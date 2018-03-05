#!/usr/bin/env python

import argparse
import os
import subprocess
import stat
import sys
import time

from graph import parse_graph, parse_files
from proc import run_proc
from mtime import read_mtimes



SCRIPT_PATH = os.path.dirname(os.path.abspath(__file__))
PROJECT_PATH = os.path.abspath(os.path.join(SCRIPT_PATH, os.pardir, os.pardir))
TOOL_PATH = os.path.join(PROJECT_PATH, 'build', 'mkcheck')



class Project(object):
    """Generic project: automake, cmake, make etc."""

    def filter(self, f):
        """Decides if the file is relevant to the project."""

        if not os.access(f, os.W_OK):
            return False
        if file == TOOL_PATH:
            return False
        return True


class CMakeProject(Project):
    """Project relying on CMake."""

    def __init__(self, projectPath, tmpPath):
        self.projectPath = projectPath
        self.tmpPath = tmpPath
        self.buildPath = os.path.join(projectPath, 'build')

        if not os.path.isdir(self.buildPath):
            raise RuntimeError('Missing build directory')

    def clean_build(self):
        """Performs a clean build of the project."""

        # Clean the project.
        self.clean()

        # Run the build with mkcheck.
        run_proc(
          [ TOOL_PATH, "--output={0}".format(self.tmpPath), "--" ] + self.BUILD,
          cwd=self.buildPath
        )

    def clean(self):
        """Cleans the project."""

        run_proc(self.CLEAN)

    def build(self):
        """Performs an incremental build."""

        run_proc(self.BUILD, cwd=self.buildPath)

    def filter(self, f):
        """Decides if the file is relevant to the project."""

        if not super(CMakeProject, self).filter(f):
            return False
        name, ext = os.path.splitext(f)
        if name.startswith(self.buildPath):
            return False
        return True


class CMakeMake(CMakeProject):
    """CMake project built using make."""

    BUILD = [ 'make', '-j1' ]
    CLEAN = [ 'make', 'clean' ]

class CMakeNinja(CMakeProject):
    """CMake project built using ninja."""

    BUILD = [ 'ninja', '-j1' ]
    CLEAN = [ 'ninja', 'clean' ]


def build_tool():
    """Builds mkcheck."""

    if os.path.isfile(os.path.join(PROJECT_PATH, 'build', 'build.ninja')):
        run_proc([ 'ninja' ], cwd=os.path.join(PROJECT_PATH, 'build'))
        return

    if os.path.isfile(os.path.join(PROJECT_PATH, 'build', 'Makefile')):
        run_proc([ 'make' ], cwd=os.path.join(PROJECT_PATH, 'build'))
        return

    raise RuntimeError('Cannot rebuild mkcheck')


def fuzz_test(project, files):
    """Find the set of inputs and outputs, as well as the graph."""

    #project.clean_build()

    inputs, outputs = parse_files(project.tmpPath)
    graph = parse_graph(project.tmpPath)
    t0 = read_mtimes(outputs)

    if len(files) == 0:
        fuzzed = sorted([f for f in inputs - outputs if project.filter(f)])
    else:
        fuzzed = [os.path.abspath(f) for f in files]

    count = len(fuzzed)
    for idx, input in zip(range(count), fuzzed):
        # Only care about the file if the user has write access to it.
        if not os.access(input, os.W_OK):
            continue

        print '[{0}/{1}] {2}:'.format(idx + 1, count, input)

        # Touch the file.
        os.utime(input, None)
        # Run the incremental build.
        project.build()

        t1 = read_mtimes(outputs)

        # Find the set of changed files.
        modified = set()
        for k, v in t0.iteritems():
            if v != t1[k]:
                modified.add(k)

        # Find expected changes.
        expected = graph.find_deps(input) & outputs

        # Report differences.
        if modified != expected:
            over = False
            under = False
            for f in modified:
                if f not in expected:
                    over = True
                    print '  +', f

            for f in expected:
                if f not in modified:
                    under = True
                    print '  -', f

            if under:
                project.clean()
                project.build()
                t1 = read_mtimes(outputs)

        t0 = t1


def query(project, files):
    """Queries the dependencies of a set of files."""

    graph = parse_graph(project.tmpPath)

    for f in files:
        path = os.path.abspath(f)
        print f, ':'
        for dep in sorted(graph.find_deps(path)):
            skip = False
            for dir in ['/proc/', '/tmp/', '/dev/']:
                if dep.startswith(dir):
                    skip = True
                    break
            if dep == path or skip:
                continue
            if dep.startswith(project.projectPath):
                dep = dep[len(project.projectPath) + 1:]
            print '  ', dep


def get_project(root, args):
    """Identifies the type of the project."""
    if os.path.isfile(os.path.join(root, 'CMakeLists.txt')):
        if os.path.isfile(os.path.join(root, 'build', 'Makefile')):
            return CMakeMake(root, args.tmp_path)
        if os.path.isfile(os.path.join(root, 'build', 'build.ninja')):
            return CMakeNinja(root, args.tmp_path)

    raise RuntimeError('Unknown project type')


def main():
    parser = argparse.ArgumentParser(description='Build Fuzzer')

    parser.add_argument(
        '--tmp-path',
        type=str,
        default='/tmp/mkcheck',
        help='Path to the temporary output file'
    )
    parser.add_argument(
        'cmd',
        metavar='COMMAND',
        type=str,
        help='Command (query/fuzz)'
    )
    parser.add_argument(
        'files',
        metavar='FILES',
        type=str,
        nargs='*',
        help='Input files'
    )

    args = parser.parse_args()

    buildDir = os.getcwd()
    project = get_project(buildDir, args)

    build_tool()

    if args.cmd == 'fuzz':
        fuzz_test(project, args.files)
        return
    if args.cmd == 'query':
        query(project, args.files)
        return

    raise RuntimeError('Unknown command: ' + args.cmd)



if __name__ == '__main__':
    main()