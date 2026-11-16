"""Home Assistant glue shared with the GivEnergy Inverter Manager integration.

Holds the code that talks to Home Assistant (web session, executor jobs, storage), never
tariff maths. Written to be copied between integrations: it imports nothing of the
integration it sits in, so the domain, cache folder and store address are arguments.
"""
