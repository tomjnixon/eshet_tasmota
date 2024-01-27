import asyncio
import eshet
from eshet import Unknown
from eshet.utils import in_task
from eshet.yarp import state_register, state_observe, replace_unknown
from yarp import Value, no_repeat
from yarp.utils import on_value
import json


# see "Configuration" in README.md
DEFAULT_CONFIG = dict(
    SetOption73=0,  # ignore button presses
    ButtonTopic=0,  # disable sending command on button which interferes with SetOption73
    TelePeriod=10,
    PowerOnState=0,  # off on power up
    PulseTime=0,
)


def repeat_last(value, time):
    """repeat the value in value every time seconds after a change or event

    this should be tidied, tested and put in yarp.temporal
    """
    from yarp.temporal import emit_at
    from yarp.temporal import make_same_type, emit_fn

    loop = asyncio.get_event_loop()

    output = make_same_type(value, inputs=[value])
    emit = emit_fn(output)

    next_time = Value(None, inputs=[value])

    @on_value(value)
    def _(value):
        next_time.value = (loop.time() + time, value)
        emit(value)

    repeat = emit_at(next_time)

    @repeat.on_event
    def on_repeat(value):
        emit(value)

        last_time, last_value = next_time.value
        next_time.value = (last_time + time, last_value)

    output.add_input(repeat)
    next_time.add_input(repeat)

    return output


class TasmotaInterface:
    def __init__(
        self,
        client,
        mqtt_client,
        topic_pattern,
        config={},
        default=None,
        enable_button_event=False,
        repeat_time=None,
    ):
        self.client = client
        self.mqtt_client = mqtt_client
        self.topic_pattern = topic_pattern
        self.default = default
        self.enable_button_event = enable_button_event
        self.repeat_time = repeat_time

        self.mqtt_callbacks = {}

        self.config = DEFAULT_CONFIG.copy()

        for k, v in config.items():
            if k not in self.config:
                raise RuntimeError(f"config value {k} is not in DEFAULT_CONFIG")
            self.config[k] = v

    # MQTT wrappers

    def topic(self, prefix, command):
        return self.topic_pattern.format(prefix=prefix, command=command)

    async def subscribe(self, prefix, command, cb):
        topic = self.topic(prefix, command)
        self.mqtt_callbacks.setdefault(topic, []).append(cb)
        await self.mqtt_client.subscribe(topic)

    async def publish(self, prefix, command, payload=b""):
        await self.mqtt_client.publish(self.topic(prefix, command), payload)

    async def msg_task(self):
        async for message in self.mqtt_client.messages:
            for cb in self.mqtt_callbacks[str(message.topic)]:
                cb(message.payload)

    # setup function for each aspect, communicating where necessary vis YARP Values

    async def setup_connected(self):
        connected_raw = Value(False)
        self.connected = no_repeat(connected_raw)

        options = {b"Online": True, b"Offline": False}

        def on_lwt(payload):
            connected_raw.value = options[payload]

        await self.subscribe("tele", "LWT", on_lwt)

        await state_register("connected", self.connected, client=self.client)

    async def setup_config(self):
        @on_value(self.connected)
        @in_task
        async def on_connected(connected):
            if connected:
                for key, value in self.config.items():
                    await self.publish("cmnd", key, str(value))

    async def setup_power_in(self):
        self.power_in = replace_unknown(
            await state_observe("power_in", client=self.client), self.default
        )

        if self.repeat_time is not None:
            self.power_in = repeat_last(self.power_in, self.repeat_time)

        @in_task
        async def set_power(value):
            await self.publish("cmnd", "Power", b"1" if value else b"0")

        def set_power_from_states(_ignored=None):
            if self.connected.value and self.power_in.value is not None:
                set_power(self.power_in.value)

        self.power_in.on_value_changed(set_power_from_states)
        self.connected.on_value_changed(set_power_from_states)

        set_power_from_states()

    async def setup_power_out(self):
        power_out = Value(eshet.Unknown)
        await state_register("power_out", no_repeat(power_out), client=self.client)

        @self.connected.on_value_changed
        def on_connected(connected):
            if not connected:
                power_out.value = Unknown

        power_out.add_input(self.connected)

        options = {b"ON": True, b"OFF": False}

        def on_power(payload):
            power_out.value = options[payload]

        await self.subscribe("stat", "POWER", on_power)

        @on_value(self.connected)
        @in_task
        async def on_connected(connected):
            # if power_in is known, Power will be sent in setup_power_in, which
            # will result in a stat message anyway
            if connected and self.power_in.value is None:
                await self.publish("cmnd", "Power")

    async def setup_tele(self, eshet_name, tasmota_name):
        value = Value(eshet.Unknown)
        await state_register(eshet_name, value, client=self.client)

        def on_state(payload):
            value.value = json.loads(payload)

        await self.subscribe("tele", tasmota_name, on_state)

        @self.connected.on_value_changed
        def on_connected(connected):
            if not connected:
                value.value = Unknown

        value.add_input(self.connected)

        return value

    async def setup_state(self):
        await self.setup_tele("state_raw", "STATE")

    async def setup_sensor(self):
        await self.setup_tele("sensor_raw", "SENSOR")

    async def setup_button(self):
        event = await self.client.event_register("on_button")

        async def on_result(payload):
            payload_json = json.loads(payload)
            if "Button1" in payload_json:
                await event(payload_json["Button1"]["Action"])

        await self.subscribe("stat", "RESULT", in_task(on_result))

    async def run(self):
        await self.setup_connected()
        await self.setup_config()
        await self.setup_power_in()
        await self.setup_power_out()
        await self.setup_state()
        await self.setup_sensor()
        if self.enable_button_event:
            await self.setup_button()

        await self.msg_task()


async def run(args):
    import aiomqtt

    async with aiomqtt.Client(args.host, port=args.port) as mqtt_client:
        eshet_client = eshet.Client(base=args.eshet_base)

        await TasmotaInterface(
            eshet_client,
            mqtt_client,
            args.pattern,
            config=dict(args.config),
            default=args.default,
            enable_button_event=args.button_event,
            repeat_time=args.repeat,
        ).run()


def parse_args():
    import argparse

    class Formatter(
        argparse.RawTextHelpFormatter, argparse.ArgumentDefaultsHelpFormatter
    ):
        """hax"""

    p = argparse.ArgumentParser(formatter_class=Formatter)

    p.add_argument("--host", default="localhost", help="MQTT host")
    p.add_argument("--port", default=1883, type=int, help="MQTT port")

    p.add_argument(
        "--default",
        type=bool,
        help=(
            "default if state_in is unknown\n"
            "if unspecified the previous value will be kept"
        ),
    )

    p.add_argument("--button-event", action="store_true", help="enable on_button event")

    p.add_argument(
        "--repeat",
        metavar="n",
        type=float,
        help=(
            "repeatedly set the power state every n seconds\n"
            "this is useful when using PulseTime"
        ),
    )

    p.add_argument(
        "--config",
        "-c",
        nargs=2,
        metavar=("config", "value"),
        action="append",
        default=[],
        help="set a configuration on connection",
    )

    p.add_argument("eshet_base", help="ESHET base path")

    p.add_argument(
        "pattern",
        help=(
            "MQTT topic pattern, with {prefix} and {command} placeholders\n\n"
            "for the default configuration, this is typically {prefix}/tasmota_XXXXXX/{command}"
        ),
    )

    return p.parse_args()


def main():
    asyncio.run(run(parse_args()))


if __name__ == "__main__":
    main()
