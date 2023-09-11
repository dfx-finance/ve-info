#!/usr/bin/env python
import json
import os
import time

from multicall import Call, Multicall
from web3 import Web3

GAUGE_CONTROLLER_ADDR = "0x3C56A223fE8F61269E25eF1116f9f185074c6C44"
DFX_DISTRIBUTOR_ADDR = "0x86E8C4e7549fBCa7eba1AefBdBc23993F721e5CA"

rpc_url = os.getenv("ETH_RPC_URL")
w3 = Web3(Web3.HTTPProvider(rpc_url))


# Web3 helpers
def load_contract(addr, abi_fn):
    with open(abi_fn) as abi_f:
        abi = json.load(abi_f)
    return w3.eth.contract(addr, abi=abi)


# Multicall handlers
def from_addr(value):
    return value


def from_bool(value):
    return value


def from_str(value):
    return value


def main():
    gauge_controller = load_contract(
        GAUGE_CONTROLLER_ADDR, "./tasks/abi/GaugeController.json"
    )

    # fetch all registered gauge addresses
    n_gauges = gauge_controller.functions.n_gauges().call()
    gauge_addrs_multi = Multicall(
        [
            Call(
                GAUGE_CONTROLLER_ADDR,
                ["gauges(uint256)(address)", i],
                [(f"gauge-{i}", from_addr)],
            )
            for i in range(n_gauges)
        ],
        _w3=w3,
    )
    gauge_addrs = gauge_addrs_multi().values()

    # fetch all gauge statuses
    gauge_statuses_multi = Multicall(
        [
            Call(
                DFX_DISTRIBUTOR_ADDR,
                ["killedGauges(address)(bool)", addr],
                [(addr, from_bool)],
            )
            for addr in gauge_addrs
        ],
        _w3=w3,
    )

    statuses = gauge_statuses_multi()
    active_gauge_addrs = list(
        filter(lambda key: statuses[key] == False, statuses)
    )  # return all keys for False values indicating gauge is not killed

    # get all gauge names
    gauges_multi = Multicall(
        [
            Call(addr, ["symbol()(string)"], [(addr, from_str)])
            for addr in active_gauge_addrs
        ],
        _w3=w3,
    )
    gauges = gauges_multi()

    # format output
    output_gauges = [{"address": key, "label": value} for key, value in gauges.items()]
    week = 7 * 24 * 60 * 60
    epoch_start = int(time.time() // week * week)  # round to latest epoch start
    with open(f"./snapshots/gauge_choices-{epoch_start}.json", "w") as json_f:
        json.dump(output_gauges, json_f, indent=4)


if __name__ == "__main__":
    main()
