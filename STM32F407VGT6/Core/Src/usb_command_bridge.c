#include "usb_command_bridge.h"
#include "robot_motion.h"
#include "usbd_cdc_if.h"
#include <stdarg.h>
#include <stdio.h>
#include <string.h>

#define USB_LINE_SIZE          96U
#define TELEMETRY_QUEUE_DEPTH  12U
#define TRACE_REPORT_MS        100U

static uint32_t gLastRxMs = 0U;
static uint8_t gCtrlTick = 0U;
static uint8_t gHaveValidFrame = 0U;
static uint8_t gPrevLinkAlive = 0U;
static uint8_t gHadTimeout = 0U;

static uint8_t gBaseCmd = CMD_STOP;
static uint8_t gBaseSpeed = 50U;
static uint8_t gLock = 0U;
static uint8_t gDirectDir[4];
static uint8_t gDirectSpeed[4];
static control_input_mode_t gLastMode = CONTROL_BASE;

static char gUsbLine[USB_LINE_SIZE];
static uint8_t gUsbLineIndex = 0U;

static char gTelemetryQueue[TELEMETRY_QUEUE_DEPTH][USB_LINE_SIZE];
static uint8_t gTelemetryHead = 0U;
static uint8_t gTelemetryCount = 0U;
static uint8_t gTelemetryTxBuffer[USB_LINE_SIZE];

static uint8_t gLastTrace[4][3];
static uint8_t gPendingTrace[4][3];
static uint8_t gHaveTrace = 0U;
static uint8_t gHavePendingTrace = 0U;
static uint32_t gLastTraceMs = 0U;

static uint8_t parse_base_cmd(const char *text, uint8_t *cmd)
{
    if (strcmp(text, "STOP") == 0) {
        *cmd = CMD_STOP;
        return 1U;
    }
    if (strcmp(text, "FWD") == 0) {
        *cmd = CMD_FWD;
        return 1U;
    }
    if (strcmp(text, "BACK") == 0) {
        *cmd = CMD_BACK;
        return 1U;
    }
    if (strcmp(text, "LEFT") == 0) {
        *cmd = CMD_LEFT;
        return 1U;
    }
    if (strcmp(text, "RIGHT") == 0) {
        *cmd = CMD_RIGHT;
        return 1U;
    }
    if (strcmp(text, "FWD_LEFT") == 0) {
        *cmd = CMD_FWD_LEFT;
        return 1U;
    }
    if (strcmp(text, "FWD_RIGHT") == 0) {
        *cmd = CMD_FWD_RIGHT;
        return 1U;
    }
    if (strcmp(text, "BACK_LEFT") == 0) {
        *cmd = CMD_BACK_LEFT;
        return 1U;
    }
    if (strcmp(text, "BACK_RIGHT") == 0) {
        *cmd = CMD_BACK_RIGHT;
        return 1U;
    }
    if (strcmp(text, "ROT_L") == 0) {
        *cmd = CMD_ROT_L;
        return 1U;
    }
    if (strcmp(text, "ROT_R") == 0) {
        *cmd = CMD_ROT_R;
        return 1U;
    }
    return 0U;
}

static uint8_t is_u8_value(int value)
{
    return (value >= 0) && (value <= 255);
}

static void note_valid_frame(void)
{
    gLastRxMs = HAL_GetTick();
    gHaveValidFrame = 1U;
}

static void queue_telemetry_line(const char *text)
{
    uint8_t index;

    if ((text == NULL) || (text[0] == '\0')) {
        return;
    }

    if (gTelemetryCount >= TELEMETRY_QUEUE_DEPTH) {
        gTelemetryHead = (uint8_t)((gTelemetryHead + 1U) % TELEMETRY_QUEUE_DEPTH);
        gTelemetryCount--;
    }

    index = (uint8_t)((gTelemetryHead + gTelemetryCount) % TELEMETRY_QUEUE_DEPTH);
    (void)snprintf(gTelemetryQueue[index], USB_LINE_SIZE, "%s\r\n", text);
    gTelemetryCount++;
}

static void queue_telemetryf(const char *fmt, ...)
{
    char line[USB_LINE_SIZE];
    va_list args;

    va_start(args, fmt);
    (void)vsnprintf(line, sizeof(line), fmt, args);
    va_end(args);
    queue_telemetry_line(line);
}

static void flush_telemetry(void)
{
    uint16_t length;

    if ((gTelemetryCount == 0U) || (CDC_TransmitReady_FS() == 0U)) {
        return;
    }

    (void)snprintf((char *)gTelemetryTxBuffer, sizeof(gTelemetryTxBuffer), "%s", gTelemetryQueue[gTelemetryHead]);
    length = (uint16_t)strlen((char *)gTelemetryTxBuffer);

    if ((length != 0U) && (CDC_Transmit_FS(gTelemetryTxBuffer, length) == (uint8_t)USBD_OK)) {
        gTelemetryHead = (uint8_t)((gTelemetryHead + 1U) % TELEMETRY_QUEUE_DEPTH);
        gTelemetryCount--;
    }
}

static void queue_trace_packets(const uint8_t packets[4][3])
{
    queue_telemetryf(
        "TRACE,UART,%02X-%02X-%02X,%02X-%02X-%02X,%02X-%02X-%02X,%02X-%02X-%02X",
        packets[0][0], packets[0][1], packets[0][2],
        packets[1][0], packets[1][1], packets[1][2],
        packets[2][0], packets[2][1], packets[2][2],
        packets[3][0], packets[3][1], packets[3][2]
    );
}

static void maybe_report_trace(void)
{
    uint8_t packets[4][3];
    uint32_t now = HAL_GetTick();

    de_robot_get_last_packets(packets);

    if ((gHavePendingTrace != 0U) && ((now - gLastTraceMs) >= TRACE_REPORT_MS)) {
        memcpy(gLastTrace, gPendingTrace, sizeof(gLastTrace));
        gHaveTrace = 1U;
        gHavePendingTrace = 0U;
        gLastTraceMs = now;
        queue_trace_packets(gLastTrace);
        return;
    }

    if ((gHaveTrace == 0U) || (memcmp(packets, gLastTrace, sizeof(gLastTrace)) != 0)) {
        if ((gHaveTrace == 0U) || ((now - gLastTraceMs) >= TRACE_REPORT_MS)) {
            memcpy(gLastTrace, packets, sizeof(gLastTrace));
            gHaveTrace = 1U;
            gLastTraceMs = now;
            gHavePendingTrace = 0U;
            queue_trace_packets(gLastTrace);
        } else {
            memcpy(gPendingTrace, packets, sizeof(gPendingTrace));
            gHavePendingTrace = 1U;
        }
    }
}

static uint8_t direct_request_changed(const uint8_t dir[4], const uint8_t speed[4])
{
    return (gLastMode != CONTROL_DIRECT) ||
           (memcmp(dir, gDirectDir, sizeof(gDirectDir)) != 0) ||
           (memcmp(speed, gDirectSpeed, sizeof(gDirectSpeed)) != 0);
}

static void remember_direct_request(const uint8_t dir[4], const uint8_t speed[4])
{
    memcpy(gDirectDir, dir, sizeof(gDirectDir));
    memcpy(gDirectSpeed, speed, sizeof(gDirectSpeed));
    gLastMode = CONTROL_DIRECT;
}

static void remember_base_request(uint8_t cmd, uint8_t speed, uint8_t lock)
{
    gBaseCmd = cmd;
    gBaseSpeed = speed;
    gLock = lock ? 1U : 0U;
    gLastMode = CONTROL_BASE;
}

static void apply_stop_command(uint8_t report_ack)
{
    uint8_t changed = (gLastMode != CONTROL_BASE) || (gBaseCmd != CMD_STOP);

    de_robot_set_base_target(CMD_STOP, gBaseSpeed, gLock);
    remember_base_request(CMD_STOP, gBaseSpeed, gLock);
    note_valid_frame();

    if ((report_ack != 0U) && (changed != 0U)) {
        queue_telemetry_line("ACK,STOP");
    }
}

static void parse_line(char *line)
{
    int speed;
    int lock;
    int parsed;
    uint8_t cmd;
    char cmdText[16];

    if (strcmp(line, "STOP") == 0) {
        apply_stop_command(1U);
        return;
    }

    {
        int speed1;
        int speed2;
        int fast;

        parsed = sscanf(line, "BASE,%15[^,],%d,%d,%d,%d", cmdText, &speed1, &speed2, &fast, &lock);
        if (parsed == 5) {
            if ((parse_base_cmd(cmdText, &cmd) != 0U) &&
                (is_u8_value(speed1) != 0U) &&
                (is_u8_value(speed2) != 0U) &&
                ((fast == 0) || (fast == 1)) &&
                ((lock == 0) || (lock == 1))) {
                uint8_t normalizedSpeed = (uint8_t)((fast != 0) ? speed2 : speed1);
                uint8_t normalizedLock = (uint8_t)lock;
                uint8_t changed = (gLastMode != CONTROL_BASE) ||
                                  (gBaseCmd != cmd) ||
                                  (gBaseSpeed != normalizedSpeed) ||
                                  (gLock != normalizedLock);

                de_robot_set_base_target(cmd, normalizedSpeed, normalizedLock);
                remember_base_request(cmd, normalizedSpeed, normalizedLock);
                note_valid_frame();

                if (changed != 0U) {
                    queue_telemetryf("ACK,BASE,%s,%u,%u", cmdText, normalizedSpeed, normalizedLock);
                }
            } else {
                queue_telemetry_line("ERR,BASE_LEGACY_FIELDS");
            }
            return;
        }
    }

    parsed = sscanf(line, "BASE,%15[^,],%d,%d", cmdText, &speed, &lock);
    if (parsed == 3) {
        if ((parse_base_cmd(cmdText, &cmd) != 0U) &&
            (is_u8_value(speed) != 0U) &&
            ((lock == 0) || (lock == 1))) {
            uint8_t normalizedSpeed = (uint8_t)speed;
            uint8_t normalizedLock = (uint8_t)lock;
            uint8_t changed = (gLastMode != CONTROL_BASE) ||
                              (gBaseCmd != cmd) ||
                              (gBaseSpeed != normalizedSpeed) ||
                              (gLock != normalizedLock);

            de_robot_set_base_target(cmd, normalizedSpeed, normalizedLock);
            remember_base_request(cmd, normalizedSpeed, normalizedLock);
            note_valid_frame();

            if (changed != 0U) {
                queue_telemetryf("ACK,BASE,%s,%u,%u", cmdText, normalizedSpeed, normalizedLock);
            }
        } else {
            queue_telemetry_line("ERR,BASE_FIELDS");
        }
        return;
    }

    if (strncmp(line, "MOTOR,", 6U) == 0) {
        int value[8];
        parsed = sscanf(line, "MOTOR,%d,%d,%d,%d,%d,%d,%d,%d",
                        &value[0], &value[1], &value[2], &value[3],
                        &value[4], &value[5], &value[6], &value[7]);
        if (parsed == 8) {
            uint8_t dir[4];
            uint8_t speedBytes[4];
            uint8_t i;

            for (i = 0U; i < 4U; i++) {
                if (((value[i * 2] != 0) && (value[i * 2] != 1)) ||
                    (is_u8_value(value[i * 2 + 1]) == 0U)) {
                    queue_telemetry_line("ERR,MOTOR_RANGE");
                    return;
                }

                dir[i] = (uint8_t)value[i * 2];
                speedBytes[i] = (uint8_t)value[i * 2 + 1];
            }

            de_robot_set_direct_targets(dir, speedBytes);
            note_valid_frame();

            if (direct_request_changed(dir, speedBytes) != 0U) {
                remember_direct_request(dir, speedBytes);
                queue_telemetryf(
                    "ACK,MOTOR,%u,%u,%u,%u,%u,%u,%u,%u",
                    dir[0], speedBytes[0], dir[1], speedBytes[1],
                    dir[2], speedBytes[2], dir[3], speedBytes[3]
                );
            }
        } else {
            queue_telemetry_line("ERR,MOTOR_FIELDS");
        }
        return;
    }

    queue_telemetryf("ERR,PARSE,%.40s", line);
}

void DeRobotDieuKhien_Init(void)
{
    memset(gDirectDir, 0, sizeof(gDirectDir));
    memset(gDirectSpeed, 0, sizeof(gDirectSpeed));
    memset(gLastTrace, 0, sizeof(gLastTrace));
    memset(gPendingTrace, 0, sizeof(gPendingTrace));
    memset(gTelemetryQueue, 0, sizeof(gTelemetryQueue));

    de_robot_di_chuyen_init();

    gLastRxMs = HAL_GetTick();
    gCtrlTick = 0U;
    gHaveValidFrame = 0U;
    gPrevLinkAlive = 0U;
    gHadTimeout = 0U;
    gBaseCmd = CMD_STOP;
    gBaseSpeed = 50U;
    gLock = 0U;
    gLastMode = CONTROL_BASE;
    gUsbLineIndex = 0U;
    gUsbLine[0] = '\0';
    gTelemetryHead = 0U;
    gTelemetryCount = 0U;
    gHaveTrace = 0U;
    gHavePendingTrace = 0U;
    gLastTraceMs = 0U;

    stop_all_motor();
    HAL_TIM_Base_Start_IT(&BASE_TICK_TIM);
}

void DeRobotDieuKhien_Task(void)
{
    if (gCtrlTick != 0U) {
        uint8_t linkAlive;

        gCtrlTick = 0U;
        linkAlive = (gHaveValidFrame != 0U) && ((HAL_GetTick() - gLastRxMs) <= 250U);
        control_step(linkAlive);
        maybe_report_trace();

        if ((linkAlive == 0U) && (gPrevLinkAlive != 0U)) {
            queue_telemetry_line("EVENT,TIMEOUT");
            gHadTimeout = 1U;
        } else if ((linkAlive != 0U) && (gPrevLinkAlive == 0U) && (gHadTimeout != 0U)) {
            queue_telemetry_line("EVENT,LINK_OK");
            gHadTimeout = 0U;
        }

        gPrevLinkAlive = linkAlive;
    }

    flush_telemetry();
}

void DeRobotDieuKhien_Tick20ms(void)
{
    gCtrlTick = 1U;
}

void DeRobotDieuKhien_UsbReceive(const uint8_t *data, uint32_t length)
{
    uint32_t i;

    for (i = 0U; i < length; i++) {
        char c = (char)data[i];

        if (c == '\r') {
            continue;
        }

        if (c == '\n') {
            gUsbLine[gUsbLineIndex] = '\0';
            if (gUsbLineIndex != 0U) {
                parse_line(gUsbLine);
            }
            gUsbLineIndex = 0U;
            continue;
        }

        if (gUsbLineIndex < (sizeof(gUsbLine) - 1U)) {
            gUsbLine[gUsbLineIndex++] = c;
        } else {
            gUsbLineIndex = 0U;
            queue_telemetry_line("ERR,USB_LINE_OVERFLOW");
        }
    }
}
