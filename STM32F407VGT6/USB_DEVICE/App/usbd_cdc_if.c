#include "usbd_cdc_if.h"
#include "usb_device.h"
#include "usb_command_bridge.h"

#define APP_RX_DATA_SIZE  256U
#define APP_TX_DATA_SIZE  256U

static int8_t CDC_Init_FS(void);
static int8_t CDC_DeInit_FS(void);
static int8_t CDC_Control_FS(uint8_t cmd, uint8_t *pbuf, uint16_t length);
static int8_t CDC_Receive_FS(uint8_t *buf, uint32_t *len);

USBD_CDC_LineCodingTypeDef LineCoding = {
    115200U,
    0x00U,
    0x00U,
    0x08U
};

static uint8_t UserRxBufferFS[APP_RX_DATA_SIZE];
static uint8_t UserTxBufferFS[APP_TX_DATA_SIZE];

USBD_CDC_ItfTypeDef USBD_Interface_fops_FS = {
    CDC_Init_FS,
    CDC_DeInit_FS,
    CDC_Control_FS,
    CDC_Receive_FS
};

static int8_t CDC_Init_FS(void)
{
    USBD_CDC_SetTxBuffer(&hUsbDeviceFS, UserTxBufferFS, 0U);
    USBD_CDC_SetRxBuffer(&hUsbDeviceFS, UserRxBufferFS);
    USBD_CDC_ReceivePacket(&hUsbDeviceFS);
    return (int8_t)USBD_OK;
}

static int8_t CDC_DeInit_FS(void)
{
    return (int8_t)USBD_OK;
}

static int8_t CDC_Control_FS(uint8_t cmd, uint8_t *pbuf, uint16_t length)
{
    (void)length;

    switch (cmd)
    {
        case CDC_SET_LINE_CODING:
            LineCoding.bitrate = (uint32_t)(pbuf[0] | (pbuf[1] << 8) | (pbuf[2] << 16) | (pbuf[3] << 24));
            LineCoding.format = pbuf[4];
            LineCoding.paritytype = pbuf[5];
            LineCoding.datatype = pbuf[6];
            break;

        case CDC_GET_LINE_CODING:
            pbuf[0] = (uint8_t)(LineCoding.bitrate);
            pbuf[1] = (uint8_t)(LineCoding.bitrate >> 8);
            pbuf[2] = (uint8_t)(LineCoding.bitrate >> 16);
            pbuf[3] = (uint8_t)(LineCoding.bitrate >> 24);
            pbuf[4] = LineCoding.format;
            pbuf[5] = LineCoding.paritytype;
            pbuf[6] = LineCoding.datatype;
            break;

        case CDC_SEND_ENCAPSULATED_COMMAND:
        case CDC_GET_ENCAPSULATED_RESPONSE:
        case CDC_SET_COMM_FEATURE:
        case CDC_GET_COMM_FEATURE:
        case CDC_CLEAR_COMM_FEATURE:
        case CDC_SET_CONTROL_LINE_STATE:
        case CDC_SEND_BREAK:
        default:
            break;
    }

    return (int8_t)USBD_OK;
}

static int8_t CDC_Receive_FS(uint8_t *buf, uint32_t *len)
{
    DeRobotDieuKhien_UsbReceive(buf, *len);
    USBD_CDC_SetRxBuffer(&hUsbDeviceFS, UserRxBufferFS);
    USBD_CDC_ReceivePacket(&hUsbDeviceFS);
    return (int8_t)USBD_OK;
}

uint8_t CDC_Transmit_FS(uint8_t *buf, uint16_t len)
{
    USBD_CDC_HandleTypeDef *hcdc = (USBD_CDC_HandleTypeDef *)hUsbDeviceFS.pClassData;

    if ((hcdc == NULL) || (hcdc->TxState != 0U)) {
        return (uint8_t)USBD_BUSY;
    }

    USBD_CDC_SetTxBuffer(&hUsbDeviceFS, buf, len);
    return USBD_CDC_TransmitPacket(&hUsbDeviceFS);
}

uint8_t CDC_TransmitReady_FS(void)
{
    USBD_CDC_HandleTypeDef *hcdc = (USBD_CDC_HandleTypeDef *)hUsbDeviceFS.pClassData;

    if (hcdc == NULL) {
        return 0U;
    }

    return (hcdc->TxState == 0U) ? 1U : 0U;
}
