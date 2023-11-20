#!/usr/bin/env python
import json
import os
import time

from multicall import Call, Multicall
from web3 import Web3

GAUGE_CONTROLLER_ADDR = "0x539A33296459ED0DeAFF9febCfD37a05B73Fa8cF"
DFX_DISTRIBUTOR_ADDR = "0xD3E7444d5DB4dDF0F9A1B52d62367C339B7bE8A9"
DFX_SENDER_ADDR = "0x7ace867b3a503C6C76834ac223993FBD8963BED2"


class Network:
    def __init__(self, name, chain_id):
        self.name = name
        self.chain_id = chain_id


# CCIP Chain Selectors
CHAIN_SELECTORS = {
    4949039107694359620: Network("arbitrum", 42161),
    4051577828743386545: Network("polygon", 137),
}

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


def from_int(value):
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

    # get all gauge types
    mainnet_gauges = {
        addr: name
        for addr, name in gauges.items()
        if name.startswith("dfx-") and name.endswith("-v3-gauge")
    }
    sidechain_gauges = {
        addr: name
        for addr, name in gauges.items()
        if not name.startswith("dfx-") or not name.endswith("-v3-gauge")
    }
    sidechain_gauge_destinations_multi = Multicall(
        [
            Call(
                DFX_SENDER_ADDR,
                ["destinations(address)(address,uint64)", addr],
                [(f"_junk", from_str), (addr, from_int)],
            )
            for addr in sidechain_gauges.keys()
        ],
        _w3=w3,
    )
    sidechain_gauge_destinations = sidechain_gauge_destinations_multi()

    # format output
    output_mainnet_gauges = [
        {"address": key, "label": value, "network": 1}
        for key, value in mainnet_gauges.items()
    ]
    output_sidechain_gauges = []
    for key, value in sidechain_gauges.items():
        selector = sidechain_gauge_destinations[key]
        dst = CHAIN_SELECTORS.get(selector)
        label = f"dfx-{value}-{dst.name}"
        output_sidechain_gauges.append(
            {
                "address": key,
                "label": label,
                "network": dst.chain_id,
            }
        )
    output_gauges = [*output_mainnet_gauges, *output_sidechain_gauges]

    week = 7 * 24 * 60 * 60
    epoch_start = int(time.time() // week * week)  # round to latest epoch start
    with open(f"./snapshots/gauge_choices-{epoch_start}.json", "w") as json_f:
        json.dump(output_gauges, json_f, indent=4)
    with open(f"./snapshots/gauge_choices-latest.json", "w") as json_f:
        json.dump(output_gauges, json_f, indent=4)


if __name__ == "__main__":
    main()
