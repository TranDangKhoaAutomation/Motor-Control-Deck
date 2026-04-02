#ifndef USB_COMMAND_BRIDGE_H
#define USB_COMMAND_BRIDGE_H

#include "main.h"
#include <stdint.h>

#ifndef BASE_TICK_TIM
#define BASE_TICK_TIM htim1
#endif

extern TIM_HandleTypeDef BASE_TICK_TIM;

void DeRobotDieuKhien_Init(void);
void DeRobotDieuKhien_Task(void);
void DeRobotDieuKhien_Tick20ms(void);
void DeRobotDieuKhien_UsbReceive(const uint8_t *data, uint32_t length);

#endif
