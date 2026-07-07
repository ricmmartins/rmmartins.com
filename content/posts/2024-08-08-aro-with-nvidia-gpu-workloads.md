---
slug: "aro-with-nvidia-gpu-workloads"
title: "ARO with Nvidia GPU Workloads"
date: 2024-08-08T10:00:00-04:00
categories:
  - Azure
  - OpenShift
tags:
  - Azure
  - ARO
  - GPU
  - Machine Learning
aliases:
  - "/2024/08/08/aro-with-nvidia-gpu-workloads/"
---

*This article was originally published at [ARO with Nvidia GPU Workloads | Red Hat Cloud Experts](https://cloud.redhat.com/experts/aro/gpu/)*

ARO guide to running Nvidia GPU workloads.

## Prerequisites

* oc cli
* Helm
* jq, moreutils, and gettext package
* An [ARO 4.14 cluster](https://cloud.redhat.com/experts/aro/terraform-install)

> **Note:** If you need to install an ARO cluster, please read our [ARO Terraform Install Guide](https://cloud.redhat.com/experts/aro/terraform-install). Please be sure if you're installing or using an existing ARO cluster that it is 4.14.x or higher.

> **Note:** Please ensure your ARO cluster was created with a valid pull secret (to verify make sure you can see the Operator Hub in the cluster's console). If not, you can follow [these](https://cloud.redhat.com/experts/aro/pull-secret) instructions.

Linux:

```bash
sudo dnf install jq moreutils gettext
```

MacOS:

```bash
brew install jq moreutils gettext helm openshift-cli
```

### Helm Prerequisites

If you plan to use Helm to deploy the GPU operator, you will need do the following:

1. Add the MOBB chart repository to your Helm

```bash
helm repo add mobb https://rh-mobb.github.io/helm-charts/
```

2. Update your repositories

```bash
helm repo update
```

## GPU Quota

All GPU quotas in Azure are 0 by default. You will need to login to the azure portal and request GPU quota. There is a lot of competition for GPU workers, so you may have to provision an ARO cluster in a region where you can actually reserve GPU.

ARO supports the following GPU workers:

* NC4as T4 v3
* NC6s v3
* NC8as T4 v3
* NC12s v3
* NC16as T4 v3
* NC24s v3
* NC24rs v3
* NC64as T4 v3

> Please remember that when you request quota that Azure is per core. To request a single NC4as T4 v3 node, you will need to request quota in groups of 4. If you wish to request an NC16as T4 v3 you will need to request quota of 16.

1. Login to Azure

Login to [portal.azure.com](https://portal.azure.com/), type "quotas" in search by, click on Compute and in the search box type "NCAsv3_T4". Select the region your cluster is in (select checkbox) and then click Request quota increase and ask for quota (I chose 8 so I can build two demo clusters of NC4as T4s). The Helm chart we use below will request a single `Standard_NC4as_T4_v3` machine.

2. Configure quota

![](/wp-content/uploads/2026/02/image-25-1024x355.png)

## Log in to your ARO cluster

1. Login to OpenShift – we'll use the kubeadmin account here but you can login with your user account as long as you have cluster-admin.

```bash
oc login <apiserver> -u kubeadmin -p <kubeadminpass>
```

## GPU Machine Set

ARO still uses Kubernetes Machinsets to create a machine set. I'm going to export the first machine set in my cluster (az 1) and use that as a template to build a single GPU machine in southcentralus region 1.

You can create the machine set the easy way using Helm, or Manually. We recommend using the Helm chart method.

### Option 1 – Helm

1. Create a new machine-set (replicas of 1), see the Chart's [values](https://github.com/rh-mobb/helm-charts/blob/main/charts/aro-gpu/values.yaml) file for configuration options

```bash
helm upgrade --install -n openshift-machine-api \
    gpu mobb/aro-gpu
```

2. Switch to the proper namespace (project):

```bash
oc project openshift-machine-api
```

3. Wait for the new GPU nodes to be available

```bash
watch oc -n openshift-machine-api get machines
```

4. Skip past **Option 2 – Manually** to Install Nvidia GPU Operator

### Option 2 – Manually

1. View existing machine sets

```bash
MACHINESET=$(oc get machineset -n openshift-machine-api -o=jsonpath='{.items[0]}' | jq -r '[.metadata.name] | @tsv')
```

2. Save a copy of example machine set

```bash
oc get machineset -n openshift-machine-api $MACHINESET -o json > gpu_machineset.json
```

3. Change the .metadata.name field to a new unique name

```bash
jq '.metadata.name = "nvidia-worker-southcentralus1"' gpu_machineset.json| sponge gpu_machineset.json
```

4. Ensure spec.replicas matches the desired replica count

```bash
jq '.spec.replicas = 1' gpu_machineset.json| sponge gpu_machineset.json
```

5. Change the matchLabels field

```bash
jq '.spec.selector.matchLabels."machine.openshift.io/cluster-api-machineset" = "nvidia-worker-southcentralus1"' gpu_machineset.json| sponge gpu_machineset.json
```

6. Change the template metadata labels

```bash
jq '.spec.template.metadata.labels."machine.openshift.io/cluster-api-machineset" = "nvidia-worker-southcentralus1"' gpu_machineset.json| sponge gpu_machineset.json
```

7. Change the vmSize to the desired GPU instance type

```bash
jq '.spec.template.spec.providerSpec.value.vmSize = "Standard_NC4as_T4_v3"' gpu_machineset.json | sponge gpu_machineset.json
```

8. Change the zone

```bash
jq '.spec.template.spec.providerSpec.value.zone = "1"' gpu_machineset.json | sponge gpu_machineset.json
```

9. Delete the .status section

```bash
jq 'del(.status)' gpu_machineset.json | sponge gpu_machineset.json
```

10. Verify the other data in the yaml file.

#### Create GPU machine set

1. Create GPU Machine set

```bash
oc create -f gpu_machineset.json
```

2. Verify GPU machine set

```bash
oc get machineset -n openshift-machine-api
oc get machine -n openshift-machine-api
```

Once the machines are provisioned (5-15 minutes), they will show as nodes:

```bash
oc get nodes
```

## Install Nvidia GPU Operator

This will create the nvidia-gpu-operator namespace, set up the operator group and install the Nvidia GPU Operator.

### Option 1 – Helm

1. Create namespaces

```bash
oc create namespace openshift-nfd
oc create namespace nvidia-gpu-operator
```

2. Use the `mobb/operatorhub` chart to deploy the needed operators

```bash
helm upgrade -n nvidia-gpu-operator nvidia-gpu-operator \
  mobb/operatorhub --install \
  --values https://raw.githubusercontent.com/rh-mobb/helm-charts/main/charts/nvidia-gpu/files/operatorhub.yaml
```

3. Wait until the two operators are running

```bash
oc wait --for=jsonpath='{.status.replicas}'=1 deployment \
  nfd-controller-manager -n openshift-nfd --timeout=600s
```

```bash
oc wait --for=jsonpath='{.status.replicas}'=1 deployment \
  gpu-operator -n nvidia-gpu-operator --timeout=600s
```

4. Install the Nvidia GPU Operator chart

```bash
helm upgrade --install -n nvidia-gpu-operator nvidia-gpu \
  mobb/nvidia-gpu --disable-openapi-validation
```

5. Skip past **Option 2 – Manually** to Validate GPU

### Option 2 – Manually

1. Create Nvidia namespace

```bash
cat <<EOF | oc apply -f -
apiVersion: v1
kind: Namespace
metadata:
  name: nvidia-gpu-operator
EOF
```

2. Create Operator Group

```bash
cat <<EOF | oc apply -f -
apiVersion: operators.coreos.com/v1
kind: OperatorGroup
metadata:
  name: nvidia-gpu-operator-group
  namespace: nvidia-gpu-operator
spec:
  targetNamespaces:
  - nvidia-gpu-operator
EOF
```

3. Get latest nvidia channel

```bash
CHANNEL=$(oc get packagemanifest gpu-operator-certified -n openshift-marketplace -o jsonpath='{.status.defaultChannel}')
```

4. Get latest nvidia package

```bash
PACKAGE=$(oc get packagemanifests/gpu-operator-certified -n openshift-marketplace -ojson | jq -r '.status.channels[] | select(.name == "'$CHANNEL'") | .currentCSV')
```

5. Create Subscription

```bash
envsubst  <<EOF | oc apply -f -
apiVersion: operators.coreos.com/v1alpha1
kind: Subscription
metadata:
  name: gpu-operator-certified
  namespace: nvidia-gpu-operator
spec:
  channel: "$CHANNEL"
  installPlanApproval: Automatic
  name: gpu-operator-certified
  source: certified-operators
  sourceNamespace: openshift-marketplace
  startingCSV: "$PACKAGE"
EOF
```

6. Wait for Operator to finish installing

#### Install Node Feature Discovery Operator

1. Set up Namespace

```bash
cat <<EOF | oc apply -f -
apiVersion: v1
kind: Namespace
metadata:
  name: openshift-nfd
EOF
```

2. Create OperatorGroup

```bash
cat <<EOF | oc apply -f -
apiVersion: operators.coreos.com/v1
kind: OperatorGroup
metadata:
  generateName: openshift-nfd-
  name: openshift-nfd
  namespace: openshift-nfd
EOF
```

3. Create Subscription

```bash
cat <<EOF | oc apply -f -
apiVersion: operators.coreos.com/v1alpha1
kind: Subscription
metadata:
  name: nfd
  namespace: openshift-nfd
spec:
  channel: "stable"
  installPlanApproval: Automatic
  name: nfd
  source: redhat-operators
  sourceNamespace: openshift-marketplace
EOF
```

4. Wait for Node Feature discovery to complete installation

5. Create NFD Instance

```bash
cat <<EOF | oc apply -f -
kind: NodeFeatureDiscovery
apiVersion: nfd.openshift.io/v1
metadata:
  name: nfd-instance
  namespace: openshift-nfd
spec:
  customConfig:
    configData: {}
  operand:
    image: >-
      registry.redhat.io/openshift4/ose-node-feature-discovery@sha256:07658ef3df4b264b02396e67af813a52ba416b47ab6e1d2d08025a350ccd2b7b
    servicePort: 12000
  workerConfig:
    configData: |
      core:
        sleepInterval: 60s
      sources:
        pci:
          deviceClassWhitelist:
            - "0200"
            - "03"
            - "12"
          deviceLabelFields:
            - "vendor"
EOF
```

#### Apply nVidia Cluster Config

1. Apply cluster config

```bash
cat <<EOF | oc apply -f -
apiVersion: nvidia.com/v1
kind: ClusterPolicy
metadata:
  name: gpu-cluster-policy
spec:
  migManager:
    enabled: true
  operator:
    defaultRuntime: crio
    initContainer: {}
    runtimeClass: nvidia
    deployGFD: true
  dcgm:
    enabled: true
  gfd: {}
  dcgmExporter:
    config:
      name: ''
  driver:
    licensingConfig:
      nlsEnabled: false
      configMapName: ''
    certConfig:
      name: ''
    kernelModuleConfig:
      name: ''
    repoConfig:
      configMapName: ''
    virtualTopology:
      config: ''
    enabled: true
    use_ocp_driver_toolkit: true
  devicePlugin: {}
  mig:
    strategy: single
  validator:
    plugin:
      env:
        - name: WITH_WORKLOAD
          value: 'true'
  nodeStatusExporter:
    enabled: true
  daemonsets: {}
  toolkit:
    enabled: true
EOF
```

## Validate GPU

1. Verify NFD can see your GPU(s)

```bash
oc describe node | egrep 'Roles|pci-10de' | grep -v master
```

You should see output like:

```
Roles:              worker
                feature.node.kubernetes.io/pci-10de.present=true
```

2. Verify node labels

```bash
oc get node -l nvidia.com/gpu.present
```

3. Wait until Cluster Policy is ready

```bash
oc wait --for=jsonpath='{.status.state}'=ready clusterpolicy \
  gpu-cluster-policy -n nvidia-gpu-operator --timeout=600s
```

4. Nvidia SMI tool verification

```bash
oc project nvidia-gpu-operator
for i in $(oc get pod -lopenshift.driver-toolkit=true --no-headers |awk '{print $1}'); do echo $i; oc exec -it $i -- nvidia-smi ; echo -e '\n' ;  done
```

![](/wp-content/uploads/2026/02/image-29-1024x456.png)

5. Create Pod to run a GPU workload

```bash
oc project nvidia-gpu-operator
cat <<EOF | oc apply -f -
apiVersion: v1
kind: Pod
metadata:
  name: cuda-vector-add
spec:
  restartPolicy: OnFailure
  containers:
    - name: cuda-vector-add
      image: "quay.io/giantswarm/nvidia-gpu-demo:latest"
      resources:
        limits:
          nvidia.com/gpu: 1
      nodeSelector:
        nvidia.com/gpu.present: true
EOF
```

6. View logs

```bash
oc logs cuda-vector-add --tail=-1
```

You should see Output like the following:

```
[Vector addition of 5000 elements]
Copy input data from the host memory to the CUDA device
CUDA kernel launch with 196 blocks of 256 threads
Copy output data from the CUDA device to the host memory
Test PASSED
Done
```

7. If successful, the pod can be deleted

```bash
oc delete pod cuda-vector-add
```
