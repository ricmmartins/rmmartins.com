---
title: "AI on Azure: a five-part series to help you choose what to build on"
slug: ai-on-azure-series
description: "My new five-part series on the Startups at Microsoft blog covers AI on Azure, from hosted models and app platforms to managed ML and GPU infrastructure."
summary: "Do you need to train a model? Which Azure services fit your application? A reading guide to my five-part AI on Azure series."
date: 2026-10-30
draft: false
categories:
  - Azure
  - AI
tags:
  - microsoft-foundry
  - azure-machine-learning
  - generative-ai
  - ai-agents
  - gpu
  - aks
translationKey: ai-no-azure-serie
---

I just published **AI on Azure**, a five-part series on the [Startups at Microsoft blog](https://techcommunity.microsoft.com/blog/startupsatmicrosoftblog).

I wrote it for developers and engineering teams working through questions like: do we need to train or fine-tune a model? Which services should we use to build the application? How much infrastructure should we manage ourselves?

Those questions lead to different decisions. Calling a hosted model, building an agent, and running a training job involve different parts of the system. The series walks through each layer so you can compare the options and understand what your team would own.

## 1. Start with the concepts

[AI on Azure 101: training, fine-tuning, inference, and where everything lives](https://techcommunity.microsoft.com/blog/startupsatmicrosoftblog/ai-on-azure-101-training-fine-tuning-inference-and-where-everything-lives/4569066/)

The first article explains training and inference, where fine-tuning fits, and how prompting and retrieval differ from changing a model's weights. A fictional support application ties the concepts together, using a predictive model for ticket priority and a language model to draft responses.

It also maps Microsoft Foundry, Fireworks on Foundry, and Azure Machine Learning to Azure resources. Start here if the service names are familiar but their boundaries are still unclear.

## 2. Choose a hosted model

[AI on Azure: models as a service](https://techcommunity.microsoft.com/blog/startupsatmicrosoftblog/ai-on-azure-models-as-a-service/4569083/)

A model API leaves you with decisions about who hosts inference, where requests are processed, and which terms apply. This part covers hosted model options in Microsoft Foundry and the deployment choices that affect capacity and billing.

Use it when you want to consume a model without operating the GPU serving stack. It explains what remains your responsibility, including evaluation, access controls, quota planning, and application costs.

## 3. Build the application around the model

[AI on Azure: platforms for apps and agents](https://techcommunity.microsoft.com/blog/startupsatmicrosoftblog/ai-on-azure-platforms-for-apps-and-agents/4569086/)

The model endpoint is one component. Your application may also need retrieval, tools, identity, and a way to evaluate results.

This article explains how the surrounding services fit together, including Foundry Agent Service, Microsoft Agent Framework, and Azure AI Search. It also discusses when a deterministic workflow is enough and when an agent is worth considering.

## 4. Train and serve models with managed platforms

[AI on Azure: managed ML](https://techcommunity.microsoft.com/blog/startupsatmicrosoftblog/ai-on-azure-managed-ml/4569087/)

For teams that need custom training or model adaptation, this part compares the roles of Azure Machine Learning, Foundry fine-tuning and managed compute, Azure Databricks, Microsoft Fabric Data Science, and Anyscale on Azure.

Training and serving are separate choices. The article looks at which parts of the model lifecycle each platform handles and which responsibilities stay with your team.

## 5. Decide when to own the infrastructure

[AI on Azure: when you own the infrastructure](https://techcommunity.microsoft.com/blog/startupsatmicrosoftblog/ai-on-azure-when-you-own-the-infrastructure/4569089)

The final part covers workloads that need control over GPU hardware or the serving stack. It discusses GPU VMs, Kubernetes, Ray, and capacity considerations, along with the operational work that comes with those choices.

Read this when you need to choose the runtime, scheduler, network, or storage yourself. A VM family and a distributed execution framework solve different problems; the article groups the options by their role.

## Where to start

If you're new to AI on Azure, follow the series from [part 1](https://techcommunity.microsoft.com/blog/startupsatmicrosoftblog/ai-on-azure-101-training-fine-tuning-inference-and-where-everything-lives/4569066/). If you already have a project, start with the layer you're deciding on: hosted inference in part 2, the application in part 3, custom ML in part 4, or infrastructure in part 5.

The articles include documentation links and call out preview features. Model availability, regions, and support terms change, so check the current documentation before committing to a production design.

You can find the series alongside my other publications on the [Projects page](/projects/) and in the [Activity Log](https://github.com/ricmmartins/activitylog).

[Leia este post em português](https://ricardomartins.com.br/ai-no-azure-serie/).
