#ifndef ROBOT_MOTION_H
#define ROBOT_MOTION_H

#include "main.h"
#include <stdint.h>

#ifndef PID_UART_HANDLE
#define PID_UART_HANDLE huart2
#endif

extern UART_HandleTypeDef PID_UART_HANDLE;

typedef enum {
    CONTROL_BASE = 0U,
    CONTROL_DIRECT = 1U
} control_input_mode_t;

#define CMD_STOP     0U
#define CMD_FWD      1U
#define CMD_BACK     2U
#define CMD_LEFT     3U
#define CMD_RIGHT    4U
#define CMD_ROT_L    5U
#define CMD_ROT_R    6U
#define CMD_FWD_LEFT   7U
#define CMD_FWD_RIGHT  8U
#define CMD_BACK_LEFT  9U
#define CMD_BACK_RIGHT 10U

void de_robot_di_chuyen_init(void);
void de_robot_set_base_target(uint8_t cmd, uint8_t speed, uint8_t lock);
void de_robot_set_direct_targets(const uint8_t dir[4], const uint8_t speed[4]);
control_input_mode_t de_robot_get_input_mode(void);
void de_robot_get_last_packets(uint8_t packets[4][3]);
void stop_all_motor(void);
void control_step(uint8_t link_alive);

#endif
