"""
Calculate Dew Point based on temperature and humidity sensors

For more details about this platform, please refer to the documentation
https://github.com/elwing00/home-assistant-dewpoint
"""
from __future__ import annotations

import logging
import asyncio

import voluptuous as vol


from homeassistant import util
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
    PLATFORM_SCHEMA,
    ENTITY_ID_FORMAT
)

from homeassistant.const import (
    TEMP_CELSIUS, 
    TEMP_FAHRENHEIT, 
    ATTR_FRIENDLY_NAME, 
    ATTR_ENTITY_ID, 
    CONF_SENSORS,
    EVENT_HOMEASSISTANT_START, 
    ATTR_TEMPERATURE,
    ATTR_NATIVE_UNIT_OF_MEASUREMENT
)

from homeassistant.core import callback
from homeassistant.helpers.entity import Entity, async_generate_entity_id
from homeassistant.helpers.event import async_track_state_change
import homeassistant.helpers.config_validation as cv


_LOGGER = logging.getLogger(__name__)

CONF_REL_HUM = 'rel_hum'

SENSOR_SCHEMA = vol.Schema({
    vol.Optional(ATTR_FRIENDLY_NAME): cv.string,
    vol.Required(ATTR_TEMPERATURE): cv.entity_id,
    vol.Required(CONF_REL_HUM): cv.entity_id
})

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_SENSORS): cv.schema_with_slug_keys(SENSOR_SCHEMA),
})


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Setup the sensor platform."""

    for device, device_config in config[CONF_SENSORS].items():
        friendly_name = device_config.get(ATTR_FRIENDLY_NAME, device)
        entity_dry_temp = device_config.get(ATTR_TEMPERATURE)
        entity_rel_hum = device_config.get(CONF_REL_HUM)

        async_add_entities([DewPointSensor(hass, device, friendly_name, entity_dry_temp, entity_rel_hum)])


class DewPointSensor(SensorEntity):

    def __init__(self, hass, device_id, name, entity_dry_temp, entity_rel_hum):
        """Initialize the sensor."""
        self.hass = hass
        self._state = None
        self.entity_id = async_generate_entity_id(
            ENTITY_ID_FORMAT, device_id, hass=hass
        )
        self._name = name
        self._attr_native_unit_of_measurement=TEMP_CELSIUS
        self._attr_device_class=SensorDeviceClass.TEMPERATURE
        self._attr_state_class=SensorStateClass.MEASUREMENT
        self._attr_icon='mdi:thermometer-lines'
        self._entity_dry_temp = entity_dry_temp
        self._entity_rel_hum = entity_rel_hum

    async def async_added_to_hass(self):
        """Register callbacks."""
        @callback
        def sensor_state_listener(entity, old_state, new_state):
            """Handle device state changes."""
            self.async_schedule_update_ha_state(True)

        @callback
        def sensor_startup(event):
            """Update template on startup."""
            async_track_state_change(
                self.hass, [self._entity_dry_temp, self._entity_rel_hum], sensor_state_listener)

            self.async_schedule_update_ha_state(True)

        self.hass.bus.async_listen_once(
            EVENT_HOMEASSISTANT_START, sensor_startup)

    @callback
    def get_dry_temp(self, entity):
        state = self.hass.states.get(entity)

        if state is None or state.state is None or state.state == 'unknown':
            _LOGGER.error('Unable to read temperature from unavailable sensor: %s', state.entity_id)
            return

        unit = state.attributes.get(ATTR_NATIVE_UNIT_OF_MEASUREMENT)
        temp = util.convert(state.state, float)

        if temp is None:
            _LOGGER.error("Unable to parse temperature sensor %s with state:"
                          " %s", state.entity_id, state.state)
            return None

        return unit_conversion.TemperatureConverter(temp)
        _LOGGER.error("Temp sensor %s has unsupported unit: %s (allowed: %s, "
                      "%s)", state.entity_id, unit, TEMP_CELSIUS,
                      TEMP_FAHRENHEIT)

        try:
            return self.hass.config.units.temperature(
                float(state.state), unit)
        except ValueError as ex:
            _LOGGER.error('Unable to read temperature from sensor: %s', ex)

    @callback
    def get_rel_hum(self, entity):
        state = self.hass.states.get(entity)

        if state is None or state.state is None or state.state == 'unknown':
            _LOGGER.error('Unable to read relative humidity from unavailable sensor: %s', state.entity_id)
            return

        unit = state.attributes.get(ATTR_NATIVE_UNIT_OF_MEASUREMENT)
        hum = util.convert(state.state, float)

        if hum is None:
            _LOGGER.error("Unable to read relative humidity from sensor %s, state: %s",
                          state.entity_id, state.state)
            return None

        if unit != '%':
            _LOGGER.error("Humidity sensor %s has unsupported unit: %s %s",
                          state.entity_id, unit, " (allowed: %)")
            return None

        if hum > 100 or hum < 0:
            _LOGGER.error("Humidity sensor %s is out of range: %s %s",
                          state.entity_id, hum, "(allowed: 0-100%)")
            return None

        return hum/100

    async def async_update(self) -> None:
        """Fetch new state data for the sensor."""

        dry_temp = self.get_dry_temp(self._entity_dry_temp)
        rel_hum = self.get_rel_hum(self._entity_rel_hum)
        
        if dry_temp is not None and rel_hum is not None:
            import psychrolib
            psychrolib.SetUnitSystem(psychrolib.SI)
            TDewPoint = psychrolib.GetTDewPointFromRelHum(dry_temp, rel_hum)
            self._attr_native_value = round(TDewPoint, 1)
