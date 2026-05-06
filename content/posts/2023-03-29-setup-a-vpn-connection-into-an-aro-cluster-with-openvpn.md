---
slug: "setup-a-vpn-connection-into-an-aro-cluster-with-openvpn"
title: "Setup a VPN Connection into an ARO Cluster with OpenVPN"
date: 2023-03-29T10:00:00-04:00
categories:
  - Azure
  - OpenShift
tags:
  - Azure
  - ARO
  - OpenVPN
  - VPN
  - Networking
aliases:
  - "/2023/03/29/setup-a-vpn-connection-into-an-aro-cluster-with-openvpn/"
---

*This article was originally published at [Setup a VPN Connection into an ARO Cluster with OpenVPN | Red Hat Cloud Experts](https://cloud.redhat.com/experts/aro/vpn/)*

When you configure an Azure Red Hat OpenShift (ARO) cluster with a private only configuration, you will need connectivity to this private network in order to access your cluster. This guide will show you how to configure a point-to-site VPN connection so you won't need to setup and configure Jump Boxes.

## Prerequisites

* a private ARO Cluster
* git
* openssl

## Create certificates to use for your VPN Connection

There are many ways and methods to create certificates for VPN, the guide below is one of the ways that works well. Note, that whatever method you use, make sure it supports "X509v3 Extended Key Usage".

1. Clone OpenVPN/easy-rsa

```bash
git clone https://github.com/OpenVPN/easy-rsa.git
```

2. Change to the easyrsa directory

```bash
cd easy-rsa/easyrsa3
```

3. Initialize the PKI

```bash
./easyrsa init-pki
```

4. Edit certificate parameters

Copy the sample values file

```bash
cp pki/vars.example pki/vars
```

Uncomment and edit the copied template with your values

```bash
vim pki/vars
```

```bash
set_var EASYRSA_REQ_COUNTRY   "US"
set_var EASYRSA_REQ_PROVINCE  "California"
set_var EASYRSA_REQ_CITY      "San Francisco"
set_var EASYRSA_REQ_ORG       "Copyleft Certificate Co"
set_var EASYRSA_REQ_EMAIL     "me@example.net"
set_var EASYRSA_REQ_OU        "My Organizational Unit"
```

Uncomment (remove the #) the following field

```bash
#set_var EASYRSA_KEY_SIZE        2048
```

5. Create the CA:

```bash
./easyrsa build-ca nopass
```

6. Generate the Server Certificate and Key

```bash
./easyrsa build-server-full server nopass
```

7. Generate Diffie-Hellman (DH) parameters

```bash
./easyrsa gen-dh
```

8. Generate client credentials

```bash
./easyrsa build-client-full azure nopass
```

9. Set environment variables for the CA certificate you just created.

```bash
CACERT=$(openssl x509 -in pki/ca.crt -outform der | base64)
```

## Set Environment Variables

```bash
AROCLUSTER=<cluster name>
ARORG=<resource group the cluster is in>
UNIQUEID=$RANDOM
LOCATION=$(az aro show --name $AROCLUSTER --resource-group $ARORG --query location -o tsv)
VNET_NAME=$(az network vnet list -g $ARORG --query '[0].name' -o tsv)
GW_NAME=${USER}_${VNET_NAME}
GW_SUBNET_PREFIX=e.g. 10.0.7.0/24 # choose a new available subnet in the VNET your cluster is in.
VPN_PREFIX=172.18.0.0/24
```

## Create an Azure Virtual Network Gateway

1. Request a public IP Address

```bash
az network public-ip create \
-n $USER-pip-$UNIQUEID \
-g $ARORG \
--allocation-method Static \
--sku Standard \
--zone 1 2 3

pip=$(az network public-ip show -g $ARORG --name $USER-pip-$UNIQUEID --query "ipAddress" -o tsv)
```

2. Create a Gateway Subnet

```bash
az network vnet subnet create \
--vnet-name $VNET_NAME \
-n GatewaySubnet \
-g $ARORG \
--address-prefix $GW_SUBNET_PREFIX
```

3. Create a virtual network gateway

```bash
az network vnet-gateway create \
--name  $GW_NAME \
--location $LOCATION \
--public-ip-address $USER-pip-$UNIQUEID \
--resource-group $ARORG \
--vnet $VNET_NAME \
--gateway-type Vpn \
--sku VpnGw3AZ \
--address-prefixes $VPN_PREFIX \
--root-cert-data pki/ca.crt \
--root-cert-name $USER-p2s \
--vpn-type RouteBased \
--vpn-gateway-generation Generation2 \
--client-protocol IkeV2 OpenVPN
```

Go grab a coffee, this takes about 15 – 20 minutes.

## Configure your OpenVPN Client

1. Retrieve the VPN Settings

From the Azure Portal – navigate to your Virtual Network Gateway, point to site configuration, and then click Download VPN Client.

![](/wp-content/uploads/2026/02/image-61-1024x425.png)

This will download a zip file containing the VPN Client.

2. Create a VPN Client Configuration

Uncompress the file you downloaded in the previous step and edit the OpenVPN/vpnconfig.ovpn file.

> Note: The next two commands assume you are still in the easyrsa3 directory.

In the vpnconfig.ovpn replace the $CLIENTCERTIFICATE line with the entire contents of:

```bash
openssl x509 -in pki/issued/azure.crt
```

Make sure to copy the -----BEGIN CERTIFICATE----- and the -----END CERTIFICATE----- lines.

Also replace $PRIVATEKEY line with the output of:

```bash
cat pki/private/azure.key
```

Make sure to copy the -----BEGIN PRIVATE KEY----- and the -----END PRIVATE KEY----- lines.

3. Add the new OpenVPN configuration file to your OpenVPN client.

> Mac users – just double click on the vpnserver.ovpn file and it will be automatically imported.

4. Connect your VPN.

![](/wp-content/uploads/2026/02/image-62.png)
