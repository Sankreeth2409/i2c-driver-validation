#include <stdint.h>

#define HALF 5            /* microseconds per half clock */
#define TIMEOUT_US 200    /* longest we wait for a slave to release SCL */

/* The only things the driver needs from the outside world */
static void (*sda_write)(int level);   /* 1 = release the line, 0 = pull it low */
static void (*scl_write)(int level);
static int  (*sda_read)(void);
static int  (*scl_read)(void);
static void (*delay_us)(int us);

static int timed_out;

void i2c_set_hal(void (*sda_w)(int), void (*scl_w)(int),
                 int (*sda_r)(void), int (*scl_r)(void), void (*delay)(int))
{
    sda_write = sda_w;
    scl_write = scl_w;
    sda_read = sda_r;
    scl_read = scl_r;
    delay_us = delay;
}

/* Release SCL and wait until it really goes high.
   A slave may hold it low (clock stretching). Give up after TIMEOUT_US. */
static void scl_high(void)
{
    int waited = 0;
    scl_write(1);
    if (timed_out) {
        return;
    }
    while (scl_read() == 0) {
        if (waited >= TIMEOUT_US) {
            timed_out = 1;
            return;
        }
        delay_us(1);
        waited++;
    }
}

static void start(void)
{
    sda_write(1);
    scl_high();
    delay_us(HALF);
    sda_write(0);
    delay_us(HALF);
    scl_write(0);
    delay_us(HALF);
}

static void repeated_start(void)
{
    sda_write(1);
    delay_us(2);
    scl_high();
    delay_us(HALF);
    sda_write(0);
    delay_us(HALF);
    scl_write(0);
    delay_us(HALF);
}

static void write_bit(int bit)
{
    sda_write(bit);
    delay_us(2);
    scl_high();
    delay_us(HALF);
    scl_write(0);
    delay_us(2);
}

static int read_ack(void)
{
    int ack;
    sda_write(1);                 /* let go so the slave can pull SDA low */
    delay_us(2);
    scl_high();
    delay_us(2);
    ack = (sda_read() == 0);      /* low = ACK, high = NACK */
    delay_us(HALF - 2);
    scl_write(0);
    delay_us(2);
    return ack;
}

static int write_byte(uint8_t byte)
{
    int i;
    for (i = 7; i >= 0; i--) {
        write_bit((byte >> i) & 1);
    }
    return read_ack();
}

/* Read one byte from the slave, then send ACK (more bytes wanted) or NACK (last byte) */
static int read_byte(int send_ack)
{
    int i, value = 0;
    sda_write(1);                 /* release SDA so the slave can drive it */
    for (i = 0; i < 8; i++) {
        delay_us(2);
        scl_high();
        delay_us(2);
        value = (value << 1) | (sda_read() ? 1 : 0);
        delay_us(HALF - 2);
        scl_write(0);
        delay_us(2);
    }
    sda_write(send_ack ? 0 : 1);  /* ACK = pull low, NACK = leave high */
    delay_us(2);
    scl_high();
    delay_us(HALF);
    scl_write(0);
    delay_us(2);
    sda_write(1);
    return value;
}

static void stop(void)
{
    sda_write(0);
    delay_us(2);
    scl_high();
    delay_us(HALF);
    sda_write(1);
    delay_us(HALF);
}

/* Returns 1 if every byte was ACKed, 0 if a byte was NACKed, -1 on timeout */
int i2c_write(uint8_t addr7, const uint8_t *data, int len)
{
    int ok, i;
    timed_out = 0;
    start();
    ok = write_byte((uint8_t)((addr7 << 1) | 0));
    for (i = 0; ok && i < len; i++) {
        ok = write_byte(data[i]);
    }
    stop();
    return timed_out ? -1 : ok;
}

/* Write wlen bytes (usually a register number), then read rlen bytes.
   Returns 1 if all ACKed, 0 if NACKed, -1 on timeout. */
int i2c_write_read(uint8_t addr7, const uint8_t *wdata, int wlen, uint8_t *rdata, int rlen)
{
    int ok, i;
    timed_out = 0;
    start();
    ok = write_byte((uint8_t)((addr7 << 1) | 0));
    for (i = 0; ok && i < wlen; i++) {
        ok = write_byte(wdata[i]);
    }
    if (ok && rlen > 0) {
        repeated_start();
        ok = write_byte((uint8_t)((addr7 << 1) | 1));
        for (i = 0; ok && i < rlen; i++) {
            rdata[i] = (uint8_t)read_byte(i < rlen - 1);
        }
    }
    stop();
    return timed_out ? -1 : ok;
}


/* Free a bus where a slave holds SDA low (e.g. after a reset in the middle of a transfer).
   Pulses SCL up to 9 times until SDA is released, then sends a STOP.
   Returns the number of clock pulses used, or -1 if the bus is still stuck. */
int i2c_recover(void)
{
    int pulses = 0;
    timed_out = 0;
    sda_write(1);
    scl_high();
    while (sda_read() == 0 && pulses < 9) {
        scl_write(0);
        delay_us(HALF);
        scl_high();
        delay_us(HALF);
        pulses++;
    }
    if (sda_read() == 0 || timed_out) {
        return -1;
    }
    scl_write(0);
    delay_us(2);
    stop();
    return pulses;
}