## Car Crash

Desc

### Attachment

- car_crash.png

### Story

I don't know how to solve this one. But I know something when I extract LSB from all the channels.

Original:

![alt text](car_crash.png)

LSB from alpha channel:
![alt text](A_0_inv.png)

Where can see something blurry in the middle of the image. Okay, that's dead end for me. But another guy told me to XOR that one with the image extracted from LSB from green channel.

LSB from green channel:
![alt text](G_0_inv.png)

When xorring together:

![alt text](A_G_xor.png)

The base64 code appear. Which decode to:

### Final Flag

```
CIT{7E3qU4wE}
```
