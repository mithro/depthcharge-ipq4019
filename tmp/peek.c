// peek <hex-addr> [<count>]
// Reads count 32-bit words from physical address via /dev/mem.
// Compile: arm-linux-gnueabi-gcc -static -O0 peek.c -o peek
//
// Critical: we read each word in its own ioread cycle so a fault on
// one word doesn't poison the others. We trap SIGBUS so a faulting
// read prints "BUS" instead of killing the process.
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <unistd.h>
#include <fcntl.h>
#include <sys/mman.h>
#include <setjmp.h>
#include <signal.h>
#include <string.h>

static sigjmp_buf jb;

static void sigbus_handler(int s)
{
    siglongjmp(jb, 1);
}

int main(int argc, char **argv)
{
    if (argc < 2) {
        fprintf(stderr, "usage: peek <hex-addr> [<count>]\n");
        return 1;
    }
    uint32_t base = strtoul(argv[1], NULL, 0);
    int count = (argc > 2) ? atoi(argv[2]) : 1;

    int fd = open("/dev/mem", O_RDONLY);
    if (fd < 0) { perror("open /dev/mem"); return 1; }

    uint32_t pagesize = sysconf(_SC_PAGESIZE);
    uint32_t pgoff = base & ~(pagesize - 1);
    uint32_t inoff = base - pgoff;
    size_t maplen = ((inoff + count * 4) + pagesize - 1) & ~(pagesize - 1);

    void *m = mmap(NULL, maplen, PROT_READ, MAP_SHARED, fd, pgoff);
    if (m == MAP_FAILED) { perror("mmap"); return 1; }

    struct sigaction sa = {0};
    sa.sa_handler = sigbus_handler;
    sigemptyset(&sa.sa_mask);
    sigaction(SIGBUS, &sa, NULL);
    sigaction(SIGSEGV, &sa, NULL);

    for (int i = 0; i < count; i++) {
        uint32_t addr = base + i * 4;
        volatile uint32_t *p = (volatile uint32_t *)((char *)m + inoff + i * 4);
        if (sigsetjmp(jb, 1) == 0) {
            uint32_t v = *p;
            printf("  0x%08x: 0x%08x\n", addr, v);
        } else {
            printf("  0x%08x: BUS\n", addr);
        }
    }
    return 0;
}
