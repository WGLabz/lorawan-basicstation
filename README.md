# Getting Started

First you need to build the `basicsstation`. Assuming you are doing this for Raspberry Pi, please run the following command.

```sh
$ make platform=rpi variant=std
```
Need to configure the app to work with `TTN` to do that open, `start.sh` and `TTN_STACK_VERSION`, `TTN_REGION` and `TC_KEY`.

You can now test the gateway with the command,

```
$ sudo sh start.sh
```
This should start the gateway and you should see the gateway as connected in TTN console.

# Autostart
`rc.local` file is used to automatically start the gateway when the Pi starts. 

```shell
$ sudo nano /etc/rc.local
```
and add the following line twords the end of it.

```js
sudo sh /home/oksbwn/lorawan-basicstation/start.sh &
```

Save it and reboot the pi or restart the rc.local service `sudo systemctl restart  rc-local.service`.
