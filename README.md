# Getting Started


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
