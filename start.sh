#!/usr/bin/env bash
# Chnage this path as per your system
cd /home/oksbwn/lorawan-basicstation/
# sleep 2m

# Set Variables
TAG_KEY="EUI"
# Defaults to TTN server v2, EU region
TTN_STACK_VERSION=3 #${TTN_STACK_VERSION:-3}
TTN_REGION="au1"
TC_KEY="NNSXS.YJSIYJZME7ADQEHVDBG5ZOVXFGQRINVJDKR26WA.JINLUCRBWUISOVXNFT42JRNDQVNOHJMK3HL5BNGEJVQEPZFYJ7HQ"

if [ -z ${EUI_ADDRESS} ] ;
 then
    TTN_EUI=$(cat /sys/class/net/eth0/address | sed -r 's/[:]+//g' | sed -e 's#\(.\{6\}\)\(.*\)#\1fffe\2#g')
 else
    echo "Using DEVICE: $EUI_ADDRESS"
    TTN_EUI=$(cat /sys/class/net/wlan0/address | sed -r 's/[:]+//g' | sed -e 's#\(.\{6\}\)\(.*\)#\1fffe\2#g')
fi


echo "Gateway EUI: $TTN_EUI"

export TAG_KEY
export TTN_STACK_VERSION
export TTN_REGION
export TC_KEY

./start_sx1301.sh
