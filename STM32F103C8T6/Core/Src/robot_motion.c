#include "robot_motion.h"
#include <string.h>

typedef struct {
    uint8_t speed[4];
    uint8_t dir[4];
} motor_tx_t;

typedef struct {
    control_input_mode_t mode;
    uint8_t base_cmd;
    uint8_t base_speed;
    uint8_t lock;
    uint8_t direct_dir[4];
    uint8_t direct_speed[4];
    uint8_t current_speed[4];
    uint8_t accel_step;
    uint8_t brake_step;
} control_state_t;

static motor_tx_t motorTx;
static uint8_t dataTx[4][3];

static control_state_t gControl = {
    CONTROL_BASE,
    CMD_STOP,
    50U,
    0U,
    {0U, 0U, 0U, 0U},
    {0U, 0U, 0U, 0U},
    {0U, 0U, 0U, 0U},
    14U,
    18U
};

static const uint8_t gDirForward[4] = {0U, 0U, 1U, 1U};
static const uint8_t gDirBackward[4] = {1U, 1U, 0U, 0U};
static const uint8_t gDirLeft[4] = {1U, 0U, 0U, 1U};
static const uint8_t gDirRight[4] = {0U, 1U, 1U, 0U};
static const uint8_t gDirRotateLeft[4] = {1U, 1U, 1U, 1U};
static const uint8_t gDirRotateRight[4] = {0U, 0U, 0U, 0U};

static void fill_dirs(uint8_t value, uint8_t targetDir[4])
{
    uint8_t i;

    for (i = 0U; i < 4U; i++) {
        targetDir[i] = value ? 1U : 0U;
    }
}

static void fill_targets(uint8_t value, uint8_t targetSpeed[4])
{
    uint8_t i;

    for (i = 0U; i < 4U; i++) {
        targetSpeed[i] = value;
    }
}

static void copy_dirs(const uint8_t source[4], uint8_t targetDir[4])
{
    uint8_t i;

    for (i = 0U; i < 4U; i++) {
        targetDir[i] = source[i] ? 1U : 0U;
    }
}

static uint8_t ramp_speed(uint8_t current, uint8_t target, uint8_t step)
{
    if (current < target) {
        uint16_t value = (uint16_t)current + step;
        return (value > target) ? target : (uint8_t)value;
    }

    if (current > target) {
        int value = (int)current - (int)step;
        return (value < (int)target) ? target : (uint8_t)value;
    }

    return current;
}

static void set_diagonal_targets(uint8_t command, uint8_t speed, uint8_t targetDir[4], uint8_t targetSpeed[4])
{
    fill_dirs(0U, targetDir);
    fill_targets(0U, targetSpeed);

    switch (command) {
        case CMD_FWD_LEFT:
            targetDir[1] = 0U;
            targetDir[3] = 1U;
            targetSpeed[1] = speed;
            targetSpeed[3] = speed;
            break;
        case CMD_FWD_RIGHT:
            targetDir[0] = 0U;
            targetDir[2] = 1U;
            targetSpeed[0] = speed;
            targetSpeed[2] = speed;
            break;
        case CMD_BACK_LEFT:
            targetDir[0] = 1U;
            targetDir[2] = 0U;
            targetSpeed[0] = speed;
            targetSpeed[2] = speed;
            break;
        case CMD_BACK_RIGHT:
            targetDir[1] = 1U;
            targetDir[3] = 0U;
            targetSpeed[1] = speed;
            targetSpeed[3] = speed;
            break;
        default:
            break;
    }
}

static void build_targets(uint8_t link_alive, uint8_t targetDir[4], uint8_t targetSpeed[4], uint8_t *stopping, uint8_t *instant_apply)
{
    uint8_t hardLockValue = gControl.lock ? 0x02U : 0x00U;

    *stopping = 0U;
    *instant_apply = 0U;
    fill_dirs(0U, targetDir);
    fill_targets(0U, targetSpeed);

    if (link_alive == 0U) {
        fill_targets(hardLockValue, targetSpeed);
        *stopping = 1U;
        return;
    }

    if (gControl.mode == CONTROL_DIRECT) {
        copy_dirs(gControl.direct_dir, targetDir);
        memcpy(targetSpeed, gControl.direct_speed, sizeof(gControl.direct_speed));
        *instant_apply = 1U;
        return;
    }

    switch (gControl.base_cmd) {
        case CMD_FWD:
            copy_dirs(gDirForward, targetDir);
            fill_targets(gControl.base_speed, targetSpeed);
            break;
        case CMD_BACK:
            copy_dirs(gDirBackward, targetDir);
            fill_targets(gControl.base_speed, targetSpeed);
            break;
        case CMD_LEFT:
            copy_dirs(gDirLeft, targetDir);
            fill_targets(gControl.base_speed, targetSpeed);
            break;
        case CMD_RIGHT:
            copy_dirs(gDirRight, targetDir);
            fill_targets(gControl.base_speed, targetSpeed);
            break;
        case CMD_FWD_LEFT:
        case CMD_FWD_RIGHT:
        case CMD_BACK_LEFT:
        case CMD_BACK_RIGHT:
            set_diagonal_targets(gControl.base_cmd, gControl.base_speed, targetDir, targetSpeed);
            break;
        case CMD_ROT_L:
            copy_dirs(gDirRotateLeft, targetDir);
            fill_targets(gControl.base_speed, targetSpeed);
            break;
        case CMD_ROT_R:
            copy_dirs(gDirRotateRight, targetDir);
            fill_targets(gControl.base_speed, targetSpeed);
            break;
        case CMD_STOP:
        default:
            fill_targets(hardLockValue, targetSpeed);
            *stopping = 1U;
            break;
    }
}

static void apply_targets(const uint8_t targetDir[4], const uint8_t targetSpeed[4], uint8_t stopping, uint8_t instant_apply)
{
    uint8_t i;

    for (i = 0U; i < 4U; i++) {
        uint8_t current = gControl.current_speed[i];
        uint8_t target = targetSpeed[i];

        if (instant_apply != 0U) {
            current = target;
        } else if (stopping != 0U) {
            current = ramp_speed(current, target, gControl.brake_step);
        } else {
            current = ramp_speed(current, target, gControl.accel_step);
        }

        gControl.current_speed[i] = current;
        motorTx.speed[i] = current;
        motorTx.dir[i] = targetDir[i] ? 1U : 0U;
    }
}

static void transmit_motor_packets(void)
{
    uint8_t i;

    for (i = 0U; i < 4U; i++) {
        uint8_t address = (uint8_t)(i + 1U);

        dataTx[i][0] = (uint8_t)(((motorTx.dir[i] & 0x01U) << 7) | (address & 0x7FU));
        dataTx[i][1] = motorTx.speed[i];
        dataTx[i][2] = 0xFFU;

        HAL_UART_Transmit(&PID_UART_HANDLE, dataTx[i], 3U, 20U);
    }
}

void de_robot_di_chuyen_init(void)
{
    memset(&motorTx, 0, sizeof(motorTx));
    memset(dataTx, 0, sizeof(dataTx));
    memset(gControl.direct_dir, 0, sizeof(gControl.direct_dir));
    memset(gControl.direct_speed, 0, sizeof(gControl.direct_speed));
    memset(gControl.current_speed, 0, sizeof(gControl.current_speed));
    gControl.mode = CONTROL_BASE;
    gControl.base_cmd = CMD_STOP;
    gControl.base_speed = 50U;
    gControl.lock = 0U;
}

void de_robot_set_base_target(uint8_t cmd, uint8_t speed, uint8_t lock)
{
    gControl.mode = CONTROL_BASE;
    gControl.base_cmd = cmd;
    gControl.base_speed = speed;
    gControl.lock = lock ? 1U : 0U;
}

void de_robot_set_direct_targets(const uint8_t dir[4], const uint8_t speed[4])
{
    uint8_t i;

    gControl.mode = CONTROL_DIRECT;

    for (i = 0U; i < 4U; i++) {
        gControl.direct_dir[i] = dir[i] ? 1U : 0U;
        gControl.direct_speed[i] = speed[i];
    }
}

control_input_mode_t de_robot_get_input_mode(void)
{
    return gControl.mode;
}

void de_robot_get_last_packets(uint8_t packets[4][3])
{
    memcpy(packets, dataTx, sizeof(dataTx));
}

void stop_all_motor(void)
{
    memset(gControl.current_speed, 0, sizeof(gControl.current_speed));
    memset(gControl.direct_dir, 0, sizeof(gControl.direct_dir));
    memset(gControl.direct_speed, 0, sizeof(gControl.direct_speed));
    memset(&motorTx, 0, sizeof(motorTx));
    gControl.mode = CONTROL_BASE;
    gControl.base_cmd = CMD_STOP;
    transmit_motor_packets();
}

void control_step(uint8_t link_alive)
{
    uint8_t targetDir[4];
    uint8_t targetSpeed[4];
    uint8_t stopping;
    uint8_t instant_apply;

    build_targets(link_alive, targetDir, targetSpeed, &stopping, &instant_apply);
    apply_targets(targetDir, targetSpeed, stopping, instant_apply);
    transmit_motor_packets();
}
