# redis-operator

## Description

The [Redis](https://www.redis.io/) operator provides in-memory data structure 
store, used as a database, cache, and message broker. This repository contains a
[Juju](https://jaas.ai/) Charm for deploying Redis on Kubernetes
clusters.

## Setup, build and deploy

A typical setup using [snaps](https://snapcraft.io/), for deployments
to a [microk8s](https://microk8s.io/) cluster can be done using the
following commands

    sudo snap install juju --classic
    sudo snap install microk8s --classic
    microk8s.enable dns storage
    juju bootstrap microk8s micro
    juju add-model redis-model
    charmcraft build
    juju deploy ./redis.charm --resource redis-image=redis:6.0

## Developing

Create and activate a virtualenv with the development requirements:

    virtualenv -p python3 venv
    source venv/bin/activate
    pip install -r requirements-dev.txt

## Testing

The Python operator framework includes a very nice harness for testing
operator behaviour without full deployment. Just `run_tests`:

    ./run_tests
