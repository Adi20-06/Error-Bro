Title: Segmentation fault (SIGSEGV)
Source: https://man7.org/linux/man-pages/man7/signal.7.html
Keywords: segmentation fault, segfault, sigsegv, core dumped, invalid memory reference, null pointer, c, c++

SIGSEGV is the signal the operating system sends to a process that touches memory it is not allowed to access. The default action is to terminate the program, and often to write a core dump file.
Common triggers: dereferencing a NULL or uninitialized pointer, reading or writing past the end of an array, using memory after free(), and very deep recursion that overflows the stack.
Useful tools: gdb (run the program, then use bt to see the call stack at the crash), valgrind, and compiling with -g -fsanitize=address to catch invalid memory access early.