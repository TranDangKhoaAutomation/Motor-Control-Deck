#include "usb_device.h"
#include "usbd_core.h"
#include "usbd_desc.h"
#include "usbd_cdc.h"
#include "usbd_cdc_if.h"

USBD_HandleTypeDef hUsbDeviceFS;

void MX_USB_DEVICE_Init(void)
{
    USBD_Init(&hUsbDeviceFS, &FS_Desc, 0U);
    USBD_RegisterClass(&hUsbDeviceFS, USBD_CDC_CLASS);
    USBD_CDC_RegisterInterface(&hUsbDeviceFS, &USBD_Interface_fops_FS);
    USBD_Start(&hUsbDeviceFS);
}
