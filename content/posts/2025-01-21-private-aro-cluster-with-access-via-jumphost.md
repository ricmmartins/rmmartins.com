---
slug: "private-aro-cluster-with-access-via-jumphost"
title: "Private ARO Cluster with Access via JumpHost"
date: 2025-01-21T10:00:00-04:00
categories:
  - Azure
  - OpenShift
tags:
  - Azure
  - ARO
  - Private Cluster
  - Networking
  - Firewall
aliases:
  - "/2025/01/21/private-aro-cluster-with-access-via-jumphost/"
---

*This article was originally published at [https://cloud.redhat.com/experts/aro/private-cluster/](https://cloud.redhat.com/experts/aro/private-cluster/)*

A Quickstart guide to deploying a Private Azure Red Hat OpenShift cluster.

## Prerequisites

### Azure CLI

*Obviously you'll need to have an Azure account to configure the CLI against.*

**MacOS**

*See [Azure Docs](https://docs.microsoft.com/en-us/cli/azure/install-azure-cli-macos) for alternative install options.*

1. Install Azure CLI using homebrew

```bash
brew update && brew install azure-cli
```

2. Install sshuttle using homebrew

```bash
brew install sshuttle
```

**Linux**

*See [Azure Docs](https://docs.microsoft.com/en-us/cli/azure/install-azure-cli-linux?pivots=dnf) for alternative install options.*

1. Import the Microsoft Keys

```bash
sudo rpm --import https://packages.microsoft.com/keys/microsoft.asc
```

2. Add the Microsoft Yum Repository

```bash
cat << EOF | sudo tee /etc/yum.repos.d/azure-cli.repo
[azure-cli]
name=Azure CLI
baseurl=https://packages.microsoft.com/yumrepos/azure-cli
enabled=1
gpgcheck=1
gpgkey=https://packages.microsoft.com/keys/microsoft.asc
EOF
```

3. Install Azure CLI

```bash
sudo dnf install -y azure-cli sshuttle
```

### Prepare Azure Account for Azure OpenShift

1. Log into the Azure CLI by running the following and then authorizing through your Web Browser

```bash
az login
```

2. Make sure you have enough Quota (change the location if you're not using East US)

```bash
az vm list-usage --location "East US" -o table
```

See [Addendum – Adding Quota to ARO account](#adding-quota-to-aro-account) if you have less than 36 Quota left for Total Regional CPUs

3. Register resource providers

```bash
az provider register -n Microsoft.RedHatOpenShift --wait
az provider register -n Microsoft.Compute --wait
az provider register -n Microsoft.Storage --wait
az provider register -n Microsoft.Authorization --wait
```

### Get Red Hat pull secret

1. Log into cloud.redhat.com
2. Browse to [https://cloud.redhat.com/openshift/install/azure/aro-provisioned](https://cloud.redhat.com/openshift/install/azure/aro-provisioned)
3. click the **Download pull secret** button and remember where you saved it, you'll reference it later.

## Deploy Azure OpenShift

### Variables and Resource Group

Set some environment variables to use later, and create an Azure Resource Group.

1. Set the following environment variables

```bash
export AZR_RESOURCE_LOCATION=eastus
export AZR_RESOURCE_GROUP=openshift-private
export AZR_CLUSTER=private-cluster
export AZR_PULL_SECRET=~/Downloads/pull-secret.txt
export NETWORK_SUBNET=10.0.0.0/20
export CONTROL_SUBNET=10.0.0.0/24
export MACHINE_SUBNET=10.0.1.0/24
export FIREWALL_SUBNET=10.0.2.0/24
export JUMPHOST_SUBNET=10.0.3.0/24
```

2. Create an Azure resource group

```bash
az group create                \
  --name $AZR_RESOURCE_GROUP   \
  --location $AZR_RESOURCE_LOCATION
```

3. Create an Azure Service Principal

```bash
AZ_SUB_ID=$(az account show --query id -o tsv)
AZ_SP_PASS=$(az ad sp create-for-rbac -n "${AZR_CLUSTER}-SP" --role contributor \
  --scopes "/subscriptions/${AZ_SUB_ID}/resourceGroups/${AZR_RESOURCE_GROUP}" \
  --query "password" -o tsv)
AZ_SP_ID=$(az ad sp list --display-name "${AZR_CLUSTER}-SP" --query "[0].appId" -o tsv)
```

### Networking

Create a virtual network with two empty subnets

1. Create virtual network

```bash
az network vnet create                                    \
  --address-prefixes $NETWORK_SUBNET                      \
  --name "$AZR_CLUSTER-aro-vnet-$AZR_RESOURCE_LOCATION"   \
  --resource-group $AZR_RESOURCE_GROUP
```

2. Create control plane subnet

```bash
az network vnet subnet create                                     \
  --resource-group $AZR_RESOURCE_GROUP                            \
  --vnet-name "$AZR_CLUSTER-aro-vnet-$AZR_RESOURCE_LOCATION"      \
  --name "$AZR_CLUSTER-aro-control-subnet-$AZR_RESOURCE_LOCATION" \
  --address-prefixes $CONTROL_SUBNET
```

3. Create machine subnet

```bash
az network vnet subnet create                                       \
  --resource-group $AZR_RESOURCE_GROUP                              \
  --vnet-name "$AZR_CLUSTER-aro-vnet-$AZR_RESOURCE_LOCATION"        \
  --name "$AZR_CLUSTER-aro-machine-subnet-$AZR_RESOURCE_LOCATION"   \
  --address-prefixes $MACHINE_SUBNET
```

```bash
az network vnet subnet update                                       \
  --name "$AZR_CLUSTER-aro-control-subnet-$AZR_RESOURCE_LOCATION"   \
  --resource-group $AZR_RESOURCE_GROUP                              \
  --vnet-name "$AZR_CLUSTER-aro-vnet-$AZR_RESOURCE_LOCATION"        \
  --disable-private-link-service-network-policies true
```

### Egress

Public and Private clusters will have `--outbound-type` defined to LoadBalancer by default. It means all clusters by default have open egress to the internet through the public load balancer.

To change the default behavior and restrict the Internet Egress you have to set `--outbound-type` to UserDefinedRouting during cluster creation, and set up traffic to run through a Firewall solution.

#### 1a. NAT Gateway

*You can skip this step if you don't need to restrict egress.*

1. Create a Public IP

```bash
az network public-ip create -g $AZR_RESOURCE_GROUP \
  -n $AZR_CLUSTER-natgw-ip   \
  --sku "Standard" --location $AZR_RESOURCE_LOCATION
```

2. Create the NAT Gateway

```bash
az network nat gateway create \
  --resource-group ${AZR_RESOURCE_GROUP} \
  --name "${AZR_CLUSTER}-natgw" \
  --location ${AZR_RESOURCE_LOCATION} \
  --public-ip-addresses "${AZR_CLUSTER}-natgw-ip"
```

3. Get the Public IP of the NAT Gateway

```bash
GW_PUBLIC_IP=$(az network public-ip show -g ${AZR_RESOURCE_GROUP} \
  -n "${AZR_CLUSTER}-natgw-ip" --query "ipAddress" -o tsv)

echo $GW_PUBLIC_IP
```

4. Reconfigure Subnets to use Nat GW

```bash
az network vnet subnet update \
  --name "${AZR_CLUSTER}-aro-control-subnet-${AZR_RESOURCE_LOCATION}"   \
  --resource-group ${AZR_RESOURCE_GROUP}                              \
  --vnet-name "${AZR_CLUSTER}-aro-vnet-${AZR_RESOURCE_LOCATION}"        \
  --nat-gateway "${AZR_CLUSTER}-natgw"
```

```bash
az network vnet subnet update \
  --name "${AZR_CLUSTER}-aro-machine-subnet-${AZR_RESOURCE_LOCATION}"   \
  --resource-group ${AZR_RESOURCE_GROUP}                              \
  --vnet-name "${AZR_CLUSTER}-aro-vnet-${AZR_RESOURCE_LOCATION}"        \
  --nat-gateway "${AZR_CLUSTER}-natgw"
```

#### 1b. Firewall + Internet Egress

*You can skip this step if you don't need to restrict egress.*

1. Make sure you have the AZ CLI firewall extensions

```bash
az extension add -n azure-firewall
az extension update -n azure-firewall
```

2. Create a firewall network, IP, and firewall

```bash
az network vnet subnet create                                 \
  -g $AZR_RESOURCE_GROUP                                      \
  --vnet-name "$AZR_CLUSTER-aro-vnet-$AZR_RESOURCE_LOCATION"  \
  -n "AzureFirewallSubnet"                                    \
  --address-prefixes $FIREWALL_SUBNET

az network public-ip create -g $AZR_RESOURCE_GROUP -n fw-ip   \
  --sku "Standard" --location $AZR_RESOURCE_LOCATION

az network firewall create -g $AZR_RESOURCE_GROUP             \
  -n aro-private -l $AZR_RESOURCE_LOCATION
```

3. Configure the firewall and configure IP Config (this may take 15 minutes)

```bash
az network firewall ip-config create -g $AZR_RESOURCE_GROUP    \
  -f aro-private -n fw-config --public-ip-address fw-ip        \
  --vnet-name "$AZR_CLUSTER-aro-vnet-$AZR_RESOURCE_LOCATION"

FWPUBLIC_IP=$(az network public-ip show -g $AZR_RESOURCE_GROUP -n fw-ip --query "ipAddress" -o tsv)
FWPRIVATE_IP=$(az network firewall show -g $AZR_RESOURCE_GROUP -n aro-private --query "ipConfigurations[0].privateIPAddress" -o tsv)

echo $FWPUBLIC_IP
echo $FWPRIVATE_IP
```

4. Create and configure a route table

```bash
az network route-table create -g $AZR_RESOURCE_GROUP --name aro-udr

sleep 10

az network route-table route create -g $AZR_RESOURCE_GROUP --name aro-udr \
  --route-table-name aro-udr --address-prefix 0.0.0.0/0                   \
  --next-hop-type VirtualAppliance --next-hop-ip-address $FWPRIVATE_IP

az network route-table route create -g $AZR_RESOURCE_GROUP --name aro-vnet   \
  --route-table-name aro-udr --address-prefix 10.0.0.0/16 --name local-route \
  --next-hop-type VirtualNetworkGateway
```

5. Create firewall rules for ARO resources

```bash
az network firewall network-rule create -g $AZR_RESOURCE_GROUP -f aro-private \
    --collection-name 'allow-https' --name allow-all                          \
    --action allow --priority 100                                             \
    --source-addresses '*' --dest-addr '*'                                    \
    --protocols 'Any' --destination-ports 1-65535
```

6. Update the subnets to use the Firewall

```bash
az network vnet subnet update -g $AZR_RESOURCE_GROUP            \
--vnet-name $AZR_CLUSTER-aro-vnet-$AZR_RESOURCE_LOCATION        \
--name "$AZR_CLUSTER-aro-control-subnet-$AZR_RESOURCE_LOCATION" \
--route-table aro-udr

az network vnet subnet update -g $AZR_RESOURCE_GROUP            \
--vnet-name $AZR_CLUSTER-aro-vnet-$AZR_RESOURCE_LOCATION        \
--name "$AZR_CLUSTER-aro-machine-subnet-$AZR_RESOURCE_LOCATION" \
--route-table aro-udr
```

### Create the cluster

This will take between 30 and 45 minutes.

```bash
az aro create                                                            \
--resource-group $AZR_RESOURCE_GROUP                                     \
--name $AZR_CLUSTER                                                      \
--vnet "$AZR_CLUSTER-aro-vnet-$AZR_RESOURCE_LOCATION"                    \
--master-subnet "$AZR_CLUSTER-aro-control-subnet-$AZR_RESOURCE_LOCATION" \
--worker-subnet "$AZR_CLUSTER-aro-machine-subnet-$AZR_RESOURCE_LOCATION" \
--apiserver-visibility Private                                           \
--ingress-visibility Private                                             \
--pull-secret @$AZR_PULL_SECRET                                          \
--client-id "${AZ_SP_ID}"                                                \
--client-secret "${AZ_SP_PASS}"
```

Be sure to add the `--outbound-type UserDefinedRouting` flag if you are not using the default routing.

### Jump Host

With the cluster in a private network, we can create a Jump host in order to connect to it. You can do this while the cluster is being created.

1. Create jump subnet

```bash
az network vnet subnet create                                \
  --resource-group $AZR_RESOURCE_GROUP                       \
  --vnet-name "$AZR_CLUSTER-aro-vnet-$AZR_RESOURCE_LOCATION" \
  --name JumpSubnet                                          \
  --address-prefixes $JUMPHOST_SUBNET                        \
  --service-endpoints Microsoft.ContainerRegistry
```

2. Create a jump host

```bash
az vm create --name jumphost                 \
    --resource-group $AZR_RESOURCE_GROUP     \
    --ssh-key-values $HOME/.ssh/id_rsa.pub   \
    --admin-username aro                     \
    --image "RedHat:RHEL:9_1:9.1.2022112113" \
    --subnet JumpSubnet                      \
    --public-ip-address jumphost-ip          \
    --public-ip-sku Standard                 \
    --vnet-name "$AZR_CLUSTER-aro-vnet-$AZR_RESOURCE_LOCATION"
```

3. Save the jump host public IP address

```bash
JUMP_IP=$(az vm list-ip-addresses -g $AZR_RESOURCE_GROUP -n jumphost -o tsv \
--query '[].virtualMachine.network.publicIpAddresses[0].ipAddress')
echo $JUMP_IP
```

4. Use sshuttle to create a ssh vpn via the jump host (use a separate terminal session)

```bash
sshuttle --dns -NHr "aro@${JUMP_IP}" $NETWORK_SUBNET
```

5. Get OpenShift console URL

```bash
APISERVER=$(az aro show              \
--name $AZR_CLUSTER                  \
--resource-group $AZR_RESOURCE_GROUP \
-o tsv --query apiserverProfile.url)
echo $APISERVER
```

6. Get OpenShift credentials

```bash
ADMINPW=$(az aro list-credentials    \
--name $AZR_CLUSTER                  \
--resource-group $AZR_RESOURCE_GROUP \
--query kubeadminPassword            \
-o tsv)
```

7. Log into OpenShift

```bash
oc login $APISERVER --username kubeadmin --password ${ADMINPW}
```

### Delete Cluster

Once you're done its a good idea to delete the cluster to ensure that you don't get a surprise bill.

1. Delete the cluster

```bash
az aro delete -y                       \
  --resource-group $AZR_RESOURCE_GROUP \
  --name $AZR_CLUSTER
```

2. Delete the Azure resource group

*Only do this if there's nothing else in the resource group.*

```bash
az group delete -y \
  --name $AZR_RESOURCE_GROUP
```

## Addendum

### Adding Quota to ARO account

![](/wp-content/uploads/2025/05/image-1024x365.png)

1. [Visit **My Quotas** in the Azure Console](https://portal.azure.com/#view/Microsoft_Azure_Capacity/QuotaMenuBlade/~/myQuotas)

2. Choose the appropriate filters:
   1. Set **Provider** to "Compute"
   2. Set **Subscription** to the subscription you are creating the cluster in
   3. Set **Region** to "East US" and uncheck the other region boxes

3. Search for the quota name that you want to increase.

4. Next to the quota name you wish to increase, click the pencil in the Adjustable column to request adjustment

5. Enter the new desired quota in the **New limit** text box. By default, a cluster will need 36 additional Regional vCPUs beyond current usage.

6. Click **Submit**. You may need to go through additional authentication.

7. Azure will review your request to adjust your quota. This may take several minutes.
