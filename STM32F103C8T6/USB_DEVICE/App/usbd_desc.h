#ifndef __USBD_DESC_H
#define __USBD_DESC_H

#ifdef __cplusplus
extern "C" {
#endif

#include "usbd_def.h"

#define DEVICE_ID1             (0x1FFFF7E8U)
#define DEVICE_ID2             (0x1FFFF7ECU)
#define DEVICE_ID3             (0x1FFFF7F0U)
#define USB_SIZ_STRING_SERIAL  0x1AU

extern USBD_DescriptorsTypeDef FS_Desc;

#ifdef __cplusplus
}
#endif

#endif
