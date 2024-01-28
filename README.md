# eshet_tasmota

A basic ESHET interface for tasmota-based smart plugs; this only controls the power
state, and reads the status (power state and energy meter).

## Usage

```
usage: eshet_tasmota [-h] [--host HOST] [--port PORT] [--default DEFAULT]
                     [--button-event] [--repeat n] [--config config value]
                     eshet_base pattern

positional arguments:
  eshet_base            ESHET base path
  pattern               MQTT topic pattern, with {prefix} and {command} placeholders
                        
                        for the default configuration, this is typically {prefix}/tasmota_XXXXXX/{command}

options:
  -h, --help            show this help message and exit
  --host HOST           MQTT host (default: localhost)
  --port PORT           MQTT port (default: 1883)
  --default DEFAULT     default if state_in is unknown
                        if unspecified the previous value will be kept (default: None)
  --button-event        enable on_button event (default: False)
  --repeat n            repeatedly set the power state every n seconds
                        this is useful when using PulseTime (default: None)
  --config config value, -c config value
                        set a configuration on connection (default: [])
```

A typical use would look something like:

```shell
eshet_tasmota /tasmota_test '{prefix}/tasmota_ABCDEF/{command}'
```

Then to set the state:

```shell
eshet publish /tasmota_test/power_in true  # or false
```

Or observe the current state:

```shell
eshet observe /tasmota_test/power_out
```

To configure the ESHET server this uses the same `ESHET_SERVER` environment
variable as other ESHET components.

## Configuration

Tasmota has many, many (many) options, and no clean way to query them all or
reset ones we don't know about to the default, so if we allowed setting
arbitrary options on the command-line (or ESHET interface), the desired config
(defaults plus specified modifications) and real config would easily get out of
sync.

To solve this, only options with defaults specified in the script can be set.
These defaults are either the actual default value, or sensible changes that
should be fine for all uses.

If you need to use an option for which a default is not provided, add it to the
`DEFAULT_CONFIG` dictionary at the top of `eshet_tasmota.py`.

## ESHET interface

Paths are relative to eshet_base:

### /power_in, observed boolean state

The interface observes this state, and updates the plug power state to match when it changes.

If `--default` is specified, it will be used when this state is unknown.
Otherwise, the previous state will be kept.

### /power_out; published boolean state

This is the actual power state of the plug. This will be unknown when disconnected.

### /connected; published boolean state

Is the interface connected to the plug or not?

### /state_raw; published JSON state

Mostly internal state published at `tele/state`. RSSI and uptime are probably the most useful bits.

### /on_button: published string event

If `--button-event` is specified, this will emit strings like
`SINGLE`/`DOUBLE`/`TRIPLE` when the button is pressed.

This will normally require `--config SetOption73 1` to publish MQTT messages on
button presses instead of changing the state.

## License

```
Copyright 2024 Thomas Nixon

This program is free software: you can redistribute it and/or modify it under
the terms of version 3 of the GNU General Public License as published by the
Free Software Foundation.

This program is distributed in the hope that it will be useful, but WITHOUT ANY
WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A
PARTICULAR PURPOSE. See the GNU General Public License for more details.

See LICENSE.
```
