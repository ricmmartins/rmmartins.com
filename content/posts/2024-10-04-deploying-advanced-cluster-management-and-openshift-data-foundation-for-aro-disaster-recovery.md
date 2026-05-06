---
slug: "deploying-advanced-cluster-management-and-openshift-data-foundation-for-aro-disaster-recovery"
title: "Deploying Advanced Cluster Management and OpenShift Data Foundation for ARO Disaster Recovery"
date: 2024-10-04T10:00:00-04:00
categories:
  - Azure
  - OpenShift
tags:
  - Azure
  - ARO
  - ACM
  - ODF
  - Disaster Recovery
  - Submariner
aliases:
  - "/2024/10/04/deploying-advanced-cluster-management-and-openshift-data-foundation-for-aro-disaster-recovery/"
---

*This article was originally published at [https://cloud.redhat.com/experts/aro/acm-odf-aro/](https://cloud.redhat.com/experts/aro/acm-odf-aro/)*

A guide to deploying Advanced Cluster Management (ACM) and OpenShift Data Foundation (ODF) for Azure Red Hat OpenShift (ARO) Disaster Recovery.

## Overview

> VolSync is not supported for ARO in ACM: [https://access.redhat.com/articles/7006295](https://access.redhat.com/articles/7006295) so if you run into issues and file a support ticket, you will receive the information that ARO is not supported.

In today's fast-paced and data-driven world, ensuring the resilience and availability of your applications and data has never been more critical. The unexpected can happen at any moment, and the ability to recover quickly and efficiently is paramount. That's where OpenShift Advanced Cluster Management (ACM) and OpenShift Data Foundation (ODF) come into play. In this guide, we will explore the deployment of ACM and ODF for disaster recovery (DR) purposes, empowering you to safeguard your applications and data across multiple clusters.

**Sample Architecture**

![Sample architecture](https://cloud.redhat.com/experts/aro/acm-odf-aro/images/sample-architecture.png)

**Hub Cluster (East US Region):**

* This is the central control and management cluster of your multi-cluster environment.
* It hosts Red Hat Advanced Cluster Management (ACM), which is a powerful tool for managing and orchestrating multiple OpenShift clusters.
* Within the Hub Cluster, you have MultiClusterHub, which is a component of ACM that facilitates the management of multiple OpenShift clusters from a single control point.
* Additionally, you have OpenShift Data Foundation (ODF) Multicluster Orchestrator in the Hub Cluster.
* The Hub Cluster shares the same Virtual Network (VNET) with the Primary Cluster, but they use different subnets within that VNET.
* VNET peering is established between the Hub Cluster's VNET and the Secondary Cluster's dedicated VNET in the Central US region.

**Primary Cluster (East US Region):**

* This cluster serves as the primary application deployment cluster.
* It has the Submariner Add-On, which enables network connectivity and service discovery between clusters.
* ODF is also deployed in the Primary Cluster, providing storage and data services to applications running in this cluster.

**Secondary Cluster (Central US Region):**

* This cluster functions as a secondary or backup cluster for disaster recovery (DR) purposes.
* Similar to the Primary Cluster, it has the Submariner Add-On to establish network connectivity.
* ODF is deployed here as well, ensuring that data can be replicated and managed across clusters.
* The Secondary Cluster resides in its own dedicated VNET in the Central US region.

## Prerequisites

* [Azure CLI](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli)
* [SShuttle](https://github.com/sshuttle/sshuttle) to create a SSH VPN (or create an [Azure VPN](https://cloud.redhat.com/experts/aro/vpn/))
* [oc cli](https://console.redhat.com/openshift/downloads#tool-oc)

#### Azure Account

1. Log into the Azure CLI

```bash
az login
```

2. Make sure you have enough Quota

```bash
az vm list-usage --location "East US" -o table
```

3. Register resource providers

```bash
az provider register -n Microsoft.RedHatOpenShift --wait
az provider register -n Microsoft.Compute --wait
az provider register -n Microsoft.Storage --wait
az provider register -n Microsoft.Authorization --wait
```

#### Red Hat pull secret

1. Log into [https://cloud.redhat.com](https://cloud.redhat.com/)
2. Browse to [https://cloud.redhat.com/openshift/install/azure/aro-provisioned](https://cloud.redhat.com/openshift/install/azure/aro-provisioned)
3. Click the **Download pull secret** button.

#### Manage Multiple Logins

```bash
rm -rf /var/tmp/acm-odf-aro-kubeconfig
touch /var/tmp/acm-odf-aro-kubeconfig
export KUBECONFIG=/var/tmp/acm-odf-aro-kubeconfig
```

## Create clusters

1. Set environment variables

```bash
export AZR_PULL_SECRET=~/Downloads/pull-secret.txt
export EAST_RESOURCE_LOCATION=eastus
export EAST_RESOURCE_GROUP=rg-eastus
export CENTRAL_RESOURCE_LOCATION=centralus
export CENTRAL_RESOURCE_GROUP=rg-centralus
```

2. Create environment variables for hub cluster

```bash
export HUB_VIRTUAL_NETWORK=10.0.0.0/20
export HUB_CLUSTER=hub-cluster
export HUB_CONTROL_SUBNET=10.0.0.0/24
export HUB_WORKER_SUBNET=10.0.1.0/24
export HUB_JUMPHOST_SUBNET=10.0.10.0/24
```

3. Set environment variables for primary cluster

```bash
export PRIMARY_CLUSTER=primary-cluster
export PRIMARY_CONTROL_SUBNET=10.0.2.0/24
export PRIMARY_WORKER_SUBNET=10.0.3.0/24
export PRIMARY_POD_CIDR=10.128.0.0/18
export PRIMARY_SERVICE_CIDR=172.30.0.0/18
```

4. Set environment variables for secondary cluster

> Note: Pod and Service CIDRs CANNOT overlap between primary and secondary clusters (because we are using Submariner).

```bash
export SECONDARY_CLUSTER=secondary-cluster
export SECONDARY_VIRTUAL_NETWORK=192.168.0.0/20
export SECONDARY_CONTROL_SUBNET=192.168.0.0/24
export SECONDARY_WORKER_SUBNET=192.168.1.0/24
export SECONDARY_JUMPHOST_SUBNET=192.168.10.0/24
export SECONDARY_POD_CIDR=10.130.0.0/18
export SECONDARY_SERVICE_CIDR=172.30.128.0/18
```

## Deploying the Hub Cluster

1. Create an Azure resource group

```bash
az group create  \
  --name $EAST_RESOURCE_GROUP  \
  --location $EAST_RESOURCE_LOCATION
```

2. Create virtual network

```bash
az network vnet create  \
  --address-prefixes $HUB_VIRTUAL_NETWORK  \
  --name "$HUB_CLUSTER-aro-vnet-$EAST_RESOURCE_LOCATION"  \
  --resource-group $EAST_RESOURCE_GROUP
```

3. Create control plane subnet

```bash
az network vnet subnet create  \
  --resource-group $EAST_RESOURCE_GROUP  \
  --vnet-name "$HUB_CLUSTER-aro-vnet-$EAST_RESOURCE_LOCATION"  \
  --name "$HUB_CLUSTER-aro-control-subnet-$EAST_RESOURCE_LOCATION"  \
  --address-prefixes $HUB_CONTROL_SUBNET
```

4. Create worker subnet

```bash
az network vnet subnet create  \
  --resource-group $EAST_RESOURCE_GROUP  \
  --vnet-name "$HUB_CLUSTER-aro-vnet-$EAST_RESOURCE_LOCATION"  \
  --name "$HUB_CLUSTER-aro-worker-subnet-$EAST_RESOURCE_LOCATION"  \
  --address-prefixes $HUB_WORKER_SUBNET
```

5. Create the cluster (30-45 minutes)

```bash
az aro create  \
    --resource-group $EAST_RESOURCE_GROUP  \
    --name $HUB_CLUSTER  \
    --vnet "$HUB_CLUSTER-aro-vnet-$EAST_RESOURCE_LOCATION"  \
    --master-subnet "$HUB_CLUSTER-aro-control-subnet-$EAST_RESOURCE_LOCATION"  \
    --worker-subnet "$HUB_CLUSTER-aro-worker-subnet-$EAST_RESOURCE_LOCATION"  \
    --version 4.12.25  \
    --apiserver-visibility Private  \
    --ingress-visibility Private  \
    --pull-secret @$AZR_PULL_SECRET
```

## Deploying the Primary cluster

1. Create control plane subnet

```bash
az network vnet subnet create  \
  --resource-group $EAST_RESOURCE_GROUP  \
  --vnet-name "$HUB_CLUSTER-aro-vnet-$EAST_RESOURCE_LOCATION"  \
  --name "$PRIMARY_CLUSTER-aro-control-subnet-$EAST_RESOURCE_LOCATION"  \
  --address-prefixes $PRIMARY_CONTROL_SUBNET
```

2. Create worker subnet

```bash
az network vnet subnet create  \
  --resource-group $EAST_RESOURCE_GROUP  \
  --vnet-name "$HUB_CLUSTER-aro-vnet-$EAST_RESOURCE_LOCATION"  \
  --name "$PRIMARY_CLUSTER-aro-worker-subnet-$EAST_RESOURCE_LOCATION"  \
  --address-prefixes $PRIMARY_WORKER_SUBNET
```

3. Create the cluster (30-45 minutes)

```bash
az aro create  \
  --resource-group $EAST_RESOURCE_GROUP  \
  --name $PRIMARY_CLUSTER  \
  --vnet "$HUB_CLUSTER-aro-vnet-$EAST_RESOURCE_LOCATION"  \
  --master-subnet "$PRIMARY_CLUSTER-aro-control-subnet-$EAST_RESOURCE_LOCATION"  \
  --worker-subnet "$PRIMARY_CLUSTER-aro-worker-subnet-$EAST_RESOURCE_LOCATION"  \
  --version 4.12.25  \
  --apiserver-visibility Private  \
  --ingress-visibility Private  \
  --pull-secret @$AZR_PULL_SECRET  \
  --pod-cidr $PRIMARY_POD_CIDR  \
  --service-cidr $PRIMARY_SERVICE_CIDR
```

## Connect to Hub and Primary Clusters

1. Create the jump subnet

```bash
az network vnet subnet create  \
  --resource-group $EAST_RESOURCE_GROUP  \
  --vnet-name "$HUB_CLUSTER-aro-vnet-$EAST_RESOURCE_LOCATION"  \
  --name jump-subnet  \
  --address-prefixes $HUB_JUMPHOST_SUBNET
```

2. Create a jump host

```bash
az vm create --name jumphost  \
    --resource-group $EAST_RESOURCE_GROUP  \
    --ssh-key-values $HOME/.ssh/id_rsa.pub  \
    --admin-username aro  \
    --image "RedHat:RHEL:9_1:9.1.2022112113"  \
    --subnet jump-subnet  \
    --public-ip-address jumphost-ip  \
    --public-ip-sku Standard  \
    --vnet-name "$HUB_CLUSTER-aro-vnet-$EAST_RESOURCE_LOCATION"
```

3. Save the jump host public IP address

```bash
EAST_JUMP_IP=$(az vm list-ip-addresses -g $EAST_RESOURCE_GROUP -n jumphost -o tsv  \
--query '[].virtualMachine.network.publicIpAddresses[0].ipAddress')
echo $EAST_JUMP_IP
```

4. Use sshuttle to create a SSH VPN via the jump host (use a separate terminal session)

```bash
sshuttle --dns -NHr "aro@${EAST_JUMP_IP}" $HUB_VIRTUAL_NETWORK
```

5. Get OpenShift API routes

```bash
HUB_APISERVER=$(az aro show  \
--name $HUB_CLUSTER  \
--resource-group $EAST_RESOURCE_GROUP  \
-o tsv --query apiserverProfile.url)

PRIMARY_APISERVER=$(az aro show  \
--name $PRIMARY_CLUSTER  \
--resource-group $EAST_RESOURCE_GROUP  \
-o tsv --query apiserverProfile.url)
```

6. Get OpenShift credentials

```bash
HUB_ADMINPW=$(az aro list-credentials  \
--name $HUB_CLUSTER  \
--resource-group $EAST_RESOURCE_GROUP  \
--query kubeadminPassword  \
-o tsv)

PRIMARY_ADMINPW=$(az aro list-credentials  \
--name $PRIMARY_CLUSTER  \
--resource-group $EAST_RESOURCE_GROUP  \
--query kubeadminPassword  \
-o tsv)
```

7. Log into Hub and configure context

```bash
oc login $HUB_APISERVER --username kubeadmin --password ${HUB_ADMINPW}
oc config rename-context $(oc config current-context) hub
oc config use hub
```

8. Log into Primary and configure context

```bash
oc login $PRIMARY_APISERVER --username kubeadmin --password ${PRIMARY_ADMINPW}
oc config rename-context $(oc config current-context) primary
oc config use primary
```

## Deploying the Secondary Cluster

1. Create an Azure resource group

```bash
az group create  \
  --name $CENTRAL_RESOURCE_GROUP  \
  --location $CENTRAL_RESOURCE_LOCATION
```

2. Create virtual network

```bash
az network vnet create  \
  --address-prefixes $SECONDARY_VIRTUAL_NETWORK  \
  --name "$SECONDARY_CLUSTER-aro-vnet-$CENTRAL_RESOURCE_LOCATION"  \
  --resource-group $CENTRAL_RESOURCE_GROUP
```

3. Create subnets and cluster (30-45 minutes)

```bash
az network vnet subnet create  \
  --resource-group $CENTRAL_RESOURCE_GROUP  \
  --vnet-name "$SECONDARY_CLUSTER-aro-vnet-$CENTRAL_RESOURCE_LOCATION"  \
  --name "$SECONDARY_CLUSTER-aro-control-subnet-$CENTRAL_RESOURCE_LOCATION"  \
  --address-prefixes $SECONDARY_CONTROL_SUBNET

az network vnet subnet create  \
  --resource-group $CENTRAL_RESOURCE_GROUP  \
  --vnet-name "$SECONDARY_CLUSTER-aro-vnet-$CENTRAL_RESOURCE_LOCATION"  \
  --name "$SECONDARY_CLUSTER-aro-worker-subnet-$CENTRAL_RESOURCE_LOCATION"  \
  --address-prefixes $SECONDARY_WORKER_SUBNET

az aro create  \
    --resource-group $CENTRAL_RESOURCE_GROUP  \
    --name $SECONDARY_CLUSTER  \
    --vnet "$SECONDARY_CLUSTER-aro-vnet-$CENTRAL_RESOURCE_LOCATION"  \
    --master-subnet "$SECONDARY_CLUSTER-aro-control-subnet-$CENTRAL_RESOURCE_LOCATION"  \
    --worker-subnet "$SECONDARY_CLUSTER-aro-worker-subnet-$CENTRAL_RESOURCE_LOCATION"  \
    --version 4.12.25  \
    --apiserver-visibility Private  \
    --ingress-visibility Private  \
    --pull-secret @$AZR_PULL_SECRET \
    --pod-cidr $SECONDARY_POD_CIDR \
    --service-cidr $SECONDARY_SERVICE_CIDR
```

## VNet Peering

Create a peering between both VNETs (Hub Cluster in EastUS and Secondary Cluster in Central US)

```bash
export RG_EASTUS=$EAST_RESOURCE_GROUP
export RG_CENTRALUS=$CENTRAL_RESOURCE_GROUP
export VNET_EASTUS=$HUB_CLUSTER-aro-vnet-$EAST_RESOURCE_LOCATION
export VNET_CENTRALUS=$SECONDARY_CLUSTER-aro-vnet-$CENTRAL_RESOURCE_LOCATION

VNET_EASTUS_ID=$(az network vnet show --resource-group $RG_EASTUS --name $VNET_EASTUS --query id --out tsv)
VNET_CENTRALUS_ID=$(az network vnet show --resource-group $RG_CENTRALUS --name $VNET_CENTRALUS --query id --out tsv)

az network vnet peering create --name "Link"-$VNET_EASTUS-"To"-$VNET_CENTRALUS  \
  --resource-group $RG_EASTUS  \
  --vnet-name $VNET_EASTUS  \
  --remote-vnet $VNET_CENTRALUS_ID  \
  --allow-vnet-access=True  \
  --allow-forwarded-traffic=True  \
  --allow-gateway-transit=True

az network vnet peering create --name "Link"-$VNET_CENTRALUS-"To"-$VNET_EASTUS  \
  --resource-group $RG_CENTRALUS  \
  --vnet-name $VNET_CENTRALUS  \
  --remote-vnet $VNET_EASTUS_ID  \
  --allow-vnet-access  \
  --allow-forwarded-traffic=True  \
  --allow-gateway-transit=True
```

## Connect to Secondary cluster

1. Create the jump subnet and host

```bash
az network vnet subnet create  \
  --resource-group $CENTRAL_RESOURCE_GROUP  \
  --vnet-name "$SECONDARY_CLUSTER-aro-vnet-$CENTRAL_RESOURCE_LOCATION"  \
  --name jump-subnet  \
  --address-prefixes $SECONDARY_JUMPHOST_SUBNET

az vm create --name jumphost  \
    --resource-group $CENTRAL_RESOURCE_GROUP  \
    --ssh-key-values $HOME/.ssh/id_rsa.pub  \
    --admin-username aro  \
    --image "RedHat:RHEL:9_1:9.1.2022112113"  \
    --subnet jump-subnet  \
    --public-ip-address jumphost-ip  \
    --public-ip-sku Standard  \
    --vnet-name "$SECONDARY_CLUSTER-aro-vnet-$CENTRAL_RESOURCE_LOCATION"
```

2. Connect via sshuttle (in a separate terminal)

```bash
CENTRAL_JUMP_IP=$(az vm list-ip-addresses -g $CENTRAL_RESOURCE_GROUP -n jumphost -o tsv  \
--query '[].virtualMachine.network.publicIpAddresses[0].ipAddress')

sshuttle --dns -NHr "aro@${CENTRAL_JUMP_IP}" $SECONDARY_VIRTUAL_NETWORK
```

3. Log into Secondary and configure context

```bash
SECONDARY_APISERVER=$(az aro show  \
--name $SECONDARY_CLUSTER  \
--resource-group $CENTRAL_RESOURCE_GROUP  \
-o tsv --query apiserverProfile.url)

SECONDARY_ADMINPW=$(az aro list-credentials  \
--name $SECONDARY_CLUSTER  \
--resource-group $CENTRAL_RESOURCE_GROUP  \
--query kubeadminPassword  \
-o tsv)

oc login $SECONDARY_APISERVER --username kubeadmin --password ${SECONDARY_ADMINPW}
oc config rename-context $(oc config current-context) secondary
oc config use secondary
```

## Setup Hub Cluster

```bash
oc config use hub
```

## Configure ACM

1. Create ACM namespace

```bash
cat << EOF | oc apply -f -
apiVersion: v1
kind: Namespace
metadata:
  name: open-cluster-management
  labels:
    openshift.io/cluster-monitoring: "true"
EOF
```

2. Create ACM Operator Group

```bash
cat << EOF | oc apply -f -
apiVersion: operators.coreos.com/v1
kind: OperatorGroup
metadata:
  name: open-cluster-management
  namespace: open-cluster-management
spec:
  targetNamespaces:
    - open-cluster-management
EOF
```

3. Install ACM version 2.8

```bash
cat << EOF | oc apply -f -
apiVersion: operators.coreos.com/v1alpha1
kind: Subscription
metadata:
  name: advanced-cluster-management
  namespace: open-cluster-management
spec:
  channel: release-2.8
  installPlanApproval: Automatic
  name: advanced-cluster-management
  source: redhat-operators
  sourceNamespace: openshift-marketplace
EOF
```

4. Check if installation succeeded

```bash
oc wait --for=jsonpath='{.status.phase}'='Succeeded' csv -n open-cluster-management \
  -l operators.coreos.com/advanced-cluster-management.open-cluster-management=''
```

5. Install MultiClusterHub instance

```bash
cat << EOF | oc apply -f -
apiVersion: operator.open-cluster-management.io/v1
kind: MultiClusterHub
metadata:
  namespace: open-cluster-management
  name: multiclusterhub
spec: {}
EOF
```

6. Check that the MultiClusterHub is running

```bash
oc wait --for=jsonpath='{.status.phase}'='Running' multiclusterhub multiclusterhub -n open-cluster-management \
  --timeout=600s
```

## Configure ODF Multicluster Orchestrator

1. Install the ODF Multicluster Orchestrator version 4.12

```bash
cat << EOF | oc apply -f -
apiVersion: operators.coreos.com/v1alpha1
kind: Subscription
metadata:
  labels:
    operators.coreos.com/odf-multicluster-orchestrator.openshift-operators: ""
  name: odf-multicluster-orchestrator
  namespace: openshift-operators
spec:
  channel: stable-4.12
  installPlanApproval: Automatic
  name: odf-multicluster-orchestrator
  source: redhat-operators
  sourceNamespace: openshift-marketplace
EOF
```

2. Check if installation succeeded

```bash
oc wait --for=jsonpath='{.status.phase}'='Succeeded' csv -n openshift-operators \
  -l operators.coreos.com/odf-multicluster-orchestrator.openshift-operators=''
```

## Import Clusters into ACM

1. Create a Managed Cluster Set

```bash
oc config use hub

export MANAGED_CLUSTER_SET_NAME=aro-clusters

cat << EOF | oc apply -f -
apiVersion: cluster.open-cluster-management.io/v1beta2
kind: ManagedClusterSet
metadata:
  name: $MANAGED_CLUSTER_SET_NAME
EOF
```

2. Retrieve token and server from primary cluster

```bash
oc config use primary
PRIMARY_API=$(oc whoami --show-server)
PRIMARY_TOKEN=$(oc whoami -t)
```

3. Retrieve token and server from secondary cluster

```bash
oc config use secondary
SECONDARY_API=$(oc whoami --show-server)
SECONDARY_TOKEN=$(oc whoami -t)
```

## Import Primary Cluster

```bash
oc config use hub

cat << EOF | oc apply -f -
apiVersion: cluster.open-cluster-management.io/v1
kind: ManagedCluster
metadata:
  name: $PRIMARY_CLUSTER
  labels:
    cluster.open-cluster-management.io/clusterset: $MANAGED_CLUSTER_SET_NAME
    cloud: auto-detect
    vendor: auto-detect
spec:
  hubAcceptsClient: true
EOF

cat << EOF | oc apply -f -
apiVersion: v1
kind: Secret
metadata:
  name: auto-import-secret
  namespace: $PRIMARY_CLUSTER
stringData:
  autoImportRetry: "2"
  token: "${PRIMARY_TOKEN}"
  server: "${PRIMARY_API}"
type: Opaque
EOF

cat << EOF | oc apply -f -
apiVersion: agent.open-cluster-management.io/v1
kind: KlusterletAddonConfig
metadata:
  name: $PRIMARY_CLUSTER
  namespace: $PRIMARY_CLUSTER
spec:
  clusterName: $PRIMARY_CLUSTER
  clusterNamespace: $PRIMARY_CLUSTER
  clusterLabels:
    cloud: auto-detect
    vendor: auto-detect
    cluster.open-cluster-management.io/clusterset: $MANAGED_CLUSTER_SET_NAME
  applicationManager:
    enabled: true
  policyController:
    enabled: true
  searchCollector:
    enabled: true
  certPolicyController:
    enabled: true
  iamPolicyController:
    enabled: true
EOF

oc get managedclusters
```

## Import Secondary Cluster

```bash
cat << EOF | oc apply -f -
apiVersion: cluster.open-cluster-management.io/v1
kind: ManagedCluster
metadata:
  name: $SECONDARY_CLUSTER
  labels:
    cluster.open-cluster-management.io/clusterset: $MANAGED_CLUSTER_SET_NAME
    cloud: auto-detect
    vendor: auto-detect
spec:
  hubAcceptsClient: true
EOF

cat << EOF | oc apply -f -
apiVersion: v1
kind: Secret
metadata:
  name: auto-import-secret
  namespace: $SECONDARY_CLUSTER
stringData:
  autoImportRetry: "2"
  token: "${SECONDARY_TOKEN}"
  server: "${SECONDARY_API}"
type: Opaque
EOF

cat << EOF | oc apply -f -
apiVersion: agent.open-cluster-management.io/v1
kind: KlusterletAddonConfig
metadata:
  name: $SECONDARY_CLUSTER
  namespace: $SECONDARY_CLUSTER
spec:
  clusterName: $SECONDARY_CLUSTER
  clusterNamespace: $SECONDARY_CLUSTER
  clusterLabels:
    cloud: auto-detect
    vendor: auto-detect
    cluster.open-cluster-management.io/clusterset: $MANAGED_CLUSTER_SET_NAME
  applicationManager:
    enabled: true
  policyController:
    enabled: true
  searchCollector:
    enabled: true
  certPolicyController:
    enabled: true
  iamPolicyController:
    enabled: true
EOF

oc get managedclusters
```

## Configure Submariner Add-On

1. Create Broker configuration

```bash
cat << EOF | oc apply -f -
apiVersion: submariner.io/v1alpha1
kind: Broker
metadata:
  name: submariner-broker
  namespace: $MANAGED_CLUSTER_SET_NAME-broker
  labels:
    cluster.open-cluster-management.io/backup: submariner
spec:
  globalnetEnabled: false
EOF
```

2. Deploy Submariner to Primary cluster

```bash
cat << EOF | oc apply -f -
apiVersion: submarineraddon.open-cluster-management.io/v1alpha1
kind: SubmarinerConfig
metadata:
  name: submariner
  namespace: $PRIMARY_CLUSTER
spec:
  IPSecNATTPort: 4500
  NATTEnable: true
  cableDriver: libreswan
  loadBalancerEnable: true
  gatewayConfig:
    gateways: 1
EOF

cat << EOF | oc apply -f -
apiVersion: addon.open-cluster-management.io/v1alpha1
kind: ManagedClusterAddOn
metadata:
     name: submariner
     namespace: $PRIMARY_CLUSTER
spec:
     installNamespace: submariner-operator
EOF
```

3. Deploy Submariner to Secondary cluster

```bash
cat << EOF | oc apply -f -
apiVersion: submarineraddon.open-cluster-management.io/v1alpha1
kind: SubmarinerConfig
metadata:
  name: submariner
  namespace: $SECONDARY_CLUSTER
spec:
  IPSecNATTPort: 4500
  NATTEnable: true
  cableDriver: libreswan
  loadBalancerEnable: true
  gatewayConfig:
    gateways: 1
EOF

cat << EOF | oc apply -f -
apiVersion: addon.open-cluster-management.io/v1alpha1
kind: ManagedClusterAddOn
metadata:
     name: submariner
     namespace: $SECONDARY_CLUSTER
spec:
     installNamespace: submariner-operator
EOF
```

4. Check connection status

```bash
oc -n $PRIMARY_CLUSTER get managedclusteraddons submariner -o yaml
```

Look for the connection established status:

```
message: The connection between clusters "primary-cluster" and "secondary-cluster"
  is established
reason: ConnectionsEstablished
status: "False"
type: SubmarinerConnectionDegraded
```

## Install ODF

**Primary Cluster**

```bash
oc config use primary
```

Follow these steps to deploy ODF: [https://cloud.redhat.com/experts/aro/odf/](https://cloud.redhat.com/experts/aro/odf/)

**Secondary Cluster**

```bash
oc config use secondary
```

Follow these steps to deploy ODF: [https://cloud.redhat.com/experts/aro/odf/](https://cloud.redhat.com/experts/aro/odf/)

## Finishing the setup of the disaster recovery solution

### Creating Disaster Recovery Policy on Hub cluster

```bash
oc config use hub

cat << EOF | oc apply -f -
apiVersion: ramendr.openshift.io/v1alpha1
kind: DRPolicy
metadata:
  name: drpolicy
spec:
  drClusters:
    - primary-cluster
    - secondary-cluster
  schedulingInterval: 5m
EOF
```

Wait for DR policy to be validated (can take up to 10 minutes):

```bash
oc get drpolicy drpolicy -o yaml
```

### Creating the Application and Failover

1. Create namespace and PlacementRule

```bash
cat <<EOF | oc apply -f -
apiVersion: v1
kind: Namespace
metadata:
 name: busybox-sample
EOF

cat <<EOF | oc apply -f -
apiVersion: apps.open-cluster-management.io/v1
kind: PlacementRule
metadata:
  name: busybox-placementrule
  namespace: busybox-sample
spec:
  clusterSelector:
    matchLabels:
      name: primary-cluster
  schedulerName: ramen
EOF
```

2. Create application with ACM

```bash
cat << EOF | oc apply -f -
apiVersion: app.k8s.io/v1beta1
kind: Application
metadata:
  name: busybox-sample
  namespace: busybox-sample
spec:
  componentKinds:
  - group: apps.open-cluster-management.io
    kind: Subscription
  descriptor: {}
  selector:
    matchExpressions:
      - key: app
        operator: In
        values:
          - busybox-sample
---
apiVersion: apps.open-cluster-management.io/v1
kind: Channel
metadata:
  annotations:
    apps.open-cluster-management.io/reconcile-rate: medium
  name: busybox-sample
  namespace: busybox-sample
spec:
  type: Git
  pathname: 'https://github.com/RamenDR/ocm-ramen-samples'
---
apiVersion: apps.open-cluster-management.io/v1
kind: Subscription
metadata:
  annotations:
    apps.open-cluster-management.io/git-branch: main
    apps.open-cluster-management.io/git-path: busybox-odr
    apps.open-cluster-management.io/reconcile-option: merge
  labels:
    app: busybox-sample
  name: busybox-sample-subscription-1
  namespace: busybox-sample
spec:
  channel: busybox-sample/busybox-sample
  placement:
    placementRef:
      kind: PlacementRule
      name: busybox-placementrule
EOF
```

3. Associate the DR policy to the application

```bash
cat <<EOF | oc apply -f -
apiVersion: ramendr.openshift.io/v1alpha1
kind: DRPlacementControl
metadata:
  labels:
    cluster.open-cluster-management.io/backup: resource
  name: busybox-placementrule-drpc
  namespace: busybox-sample
spec:
  drPolicyRef:
    name: drpolicy
  placementRef:
    kind: PlacementRule
    name: busybox-placementrule
    namespace: busybox-sample
  preferredCluster: $PRIMARY_CLUSTER
  pvcSelector:
    matchLabels:
      appname: busybox-sample
EOF
```

4. Failover sample application to secondary cluster

```bash
cat <<EOF | oc apply -f -
apiVersion: ramendr.openshift.io/v1alpha1
kind: DRPlacementControl
metadata:
  labels:
    cluster.open-cluster-management.io/backup: resource
  name: busybox-placementrule-drpc
  namespace: busybox-sample
spec:
  action: Failover
  failoverCluster: $SECONDARY_CLUSTER
  drPolicyRef:
    name: drpolicy
  placementRef:
    kind: PlacementRule
    name: busybox-placementrule
    namespace: busybox-sample
  pvcSelector:
    matchLabels:
      appname: busybox-sample
EOF
```

5. Verify application runs in secondary cluster

```bash
oc config use secondary
oc get pods -n busybox-sample
```

## Cleanup

```bash
az aro delete -y  \
  --resource-group rg-eastus  \
  --name hub-cluster

az aro delete -y  \
  --resource-group rg-eastus  \
  --name primary-cluster

az group delete --name rg-eastus

az aro delete -y  \
  --resource-group rg-centralus  \
  --name secondary-cluster

az group delete --name rg-centralus
```

## Additional reference resources

* [Virtual Network Peering](https://learn.microsoft.com/en-us/azure/virtual-network/virtual-network-peering-overview)
* [Regional-DR solution for OpenShift Data Foundation](https://access.redhat.com/documentation/en-us/red_hat_openshift_data_foundation/4.12/html/configuring_openshift_data_foundation_disaster_recovery_for_openshift_workloads/rdr-solution)
* [Private ARO Cluster with access via JumpHost](https://mobb.ninja/docs/aro/private-cluster/)
* [Deploy ACM Submariner for connect overlay networks ARO – ROSA clusters](https://mobb.ninja/docs/redhat/acm/submariner/aro/)
* [Configure ARO with OpenShift Data Foundation](https://mobb.ninja/docs/aro/odf/)
* [OpenShift Regional Disaster Recovery with Advanced Cluster Management](https://red-hat-storage.github.io/ocs-training/training/ocs4/odf4-multisite-ramen.html#_create_drplacementcontrol_resource)
