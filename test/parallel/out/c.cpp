#include <stdio.h>
#include "a.h"
#include "b.h"

void c()
{
  a();
  b();
  printf("c\n");
}

