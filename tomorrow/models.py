"""Pydantic models for Tomorrow.io API and internal data structures.

Models are validated against the actual API response structure in
wheather-api-response.json to ensure compatibility.
"""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, ConfigDict


class TimelineValues(BaseModel):
    """Weather values from Tomorrow.io API timeline response.
    
    This model represents the 'values' object from the API response,
    containing all available weather metrics. All fields are optional
    since the API may not return every field in every response.
    
    Field names use camelCase aliases to match the API response,
    with snake_case Python attribute names for PEP 8 compliance.
    """
    model_config = ConfigDict(populate_by_name=True)
    
    # Temperature fields
    temperature: Optional[float] = Field(None, alias="temperature", description="Temperature in Celsius")
    temperature_apparent: Optional[float] = Field(None, alias="temperatureApparent", description="Feels-like temperature in Celsius")
    
    # Wind fields
    wind_speed: Optional[float] = Field(None, alias="windSpeed", description="Wind speed in m/s")
    wind_gust: Optional[float] = Field(None, alias="windGust", description="Wind gust speed in m/s")
    wind_direction: Optional[int] = Field(None, alias="windDirection", description="Wind direction in degrees (0-360)")
    
    # Atmospheric conditions
    humidity: Optional[float] = Field(None, alias="humidity", description="Relative humidity as percentage (0-100)")
    dew_point: Optional[float] = Field(None, alias="dewPoint", description="Dew point in Celsius")
    cloud_cover: Optional[float] = Field(None, alias="cloudCover", description="Cloud cover as percentage (0-100)")
    cloud_base: Optional[float] = Field(None, alias="cloudBase", description="Cloud base height in km")
    cloud_ceiling: Optional[float] = Field(None, alias="cloudCeiling", description="Cloud ceiling height in km")
    visibility: Optional[float] = Field(None, alias="visibility", description="Visibility in km")
    
    # Precipitation fields
    precipitation_probability: Optional[float] = Field(None, alias="precipitationProbability", description="Precipitation probability as percentage (0-100)")
    rain_intensity: Optional[float] = Field(None, alias="rainIntensity", description="Rain intensity in mm/hr")
    rain_accumulation: Optional[float] = Field(None, alias="rainAccumulation", description="Rain accumulation in mm")
    freezing_rain_intensity: Optional[float] = Field(None, alias="freezingRainIntensity", description="Freezing rain intensity in mm/hr")
    sleet_intensity: Optional[float] = Field(None, alias="sleetIntensity", description="Sleet intensity in mm/hr")
    sleet_accumulation: Optional[float] = Field(None, alias="sleetAccumulation", description="Sleet accumulation in mm")
    sleet_accumulation_lwe: Optional[float] = Field(None, alias="sleetAccumulationLwe", description="Sleet accumulation liquid water equivalent in mm")
    snow_intensity: Optional[float] = Field(None, alias="snowIntensity", description="Snow intensity in mm/hr")
    snow_accumulation: Optional[float] = Field(None, alias="snowAccumulation", description="Snow accumulation in mm")
    snow_accumulation_lwe: Optional[float] = Field(None, alias="snowAccumulationLwe", description="Snow accumulation liquid water equivalent in mm")
    snow_depth: Optional[float] = Field(None, alias="snowDepth", description="Snow depth in cm")
    ice_accumulation: Optional[float] = Field(None, alias="iceAccumulation", description="Ice accumulation in mm")
    ice_accumulation_lwe: Optional[float] = Field(None, alias="iceAccumulationLwe", description="Ice accumulation liquid water equivalent in mm")
    evapotranspiration: Optional[float] = Field(None, alias="evapotranspiration", description="Evapotranspiration in mm")
    
    # Pressure fields
    pressure_sea_level: Optional[float] = Field(None, alias="pressureSeaLevel", description="Sea level pressure in hPa")
    pressure_surface_level: Optional[float] = Field(None, alias="pressureSurfaceLevel", description="Surface level pressure in hPa")
    altimeter_setting: Optional[float] = Field(None, alias="altimeterSetting", description="Altimeter setting in hPa")
    
    # Weather codes
    weather_code: Optional[int] = Field(None, alias="weatherCode", description="Tomorrow.io weather condition code")
    
    # UV index
    uv_index: Optional[int] = Field(None, alias="uvIndex", description="UV index (0-11+)")
    uv_health_concern: Optional[int] = Field(None, alias="uvHealthConcern", description="UV health concern level (0-5)")


class TimelineEntry(BaseModel):
    """A single timeline entry from the Tomorrow.io API.
    
    Contains a timestamp and the weather values for that time.
    """
    model_config = ConfigDict(populate_by_name=True)
    
    time: datetime = Field(..., alias="time", description="Timestamp of the weather reading (ISO 8601)")
    values: TimelineValues = Field(..., alias="values", description="Weather values for this timestamp")


class TimelinesResponse(BaseModel):
    """Root response structure from Tomorrow.io /timelines API.
    
    Contains timelines for different granularities (minutely, hourly, daily).
    Each timeline is a list of timeline entries with timestamps and values.
    """
    model_config = ConfigDict(populate_by_name=True)
    
    timelines: dict[Literal["minutely", "hourly", "daily"], list[TimelineEntry]] = Field(
        ...,
        alias="timelines",
        description="Weather timelines by granularity"
    )


# ============================================================================
# Internal Models for Database Operations
# ============================================================================

class Location(BaseModel):
    """Internal model representing a geographic location.
    
    Maps directly to the locations database table.
    """
    model_config = ConfigDict(from_attributes=True)
    
    id: int = Field(..., description="Unique location ID")
    lat: float = Field(..., description="Latitude coordinate (-90 to 90)")
    lon: float = Field(..., description="Longitude coordinate (-180 to 180)")
    name: Optional[str] = Field(None, description="Optional location name/description")
    is_active: bool = Field(True, description="Whether this location is active for data collection")
    created_at: Optional[datetime] = Field(None, description="When the location was added")
    
    def __hash__(self):
        """Enable using Location in sets and as dict keys."""
        return hash((self.lat, self.lon))
    
    def __eq__(self, other):
        """Enable equality comparison based on coordinates."""
        if not isinstance(other, Location):
            return False
        return self.lat == other.lat and self.lon == other.lon


class WeatherReading(BaseModel):
    """Internal model representing a single weather reading.
    
    Maps directly to the weather_data database table.
    Used for inserting data into the database.
    """
    model_config = ConfigDict(from_attributes=True)
    
    location_id: int = Field(..., description="Foreign key to locations table")
    timestamp: datetime = Field(..., description="Timestamp of the weather reading")
    
    # Weather data fields (all optional for flexibility)
    temperature: Optional[float] = Field(None, description="Temperature in Celsius")
    temperature_apparent: Optional[float] = Field(None, description="Feels-like temperature in Celsius")
    wind_speed: Optional[float] = Field(None, description="Wind speed in m/s")
    wind_gust: Optional[float] = Field(None, description="Wind gust speed in m/s")
    wind_direction: Optional[int] = Field(None, description="Wind direction in degrees (0-360)")
    humidity: Optional[float] = Field(None, description="Relative humidity as percentage")
    precipitation_probability: Optional[float] = Field(None, description="Precipitation probability as percentage")
    weather_code: Optional[int] = Field(None, description="Tomorrow.io weather condition code")
    cloud_cover: Optional[float] = Field(None, description="Cloud cover as percentage")
    visibility: Optional[float] = Field(None, description="Visibility in km")
    pressure_sea_level: Optional[float] = Field(None, description="Sea level pressure in hPa")
    pressure_surface_level: Optional[float] = Field(None, description="Surface level pressure in hPa")
    dew_point: Optional[float] = Field(None, description="Dew point in Celsius")
    uv_index: Optional[int] = Field(None, description="UV index (0-11+)")
    
    # Metadata
    data_granularity: Literal["minutely", "hourly", "daily"] = Field(
        ..., description="Data granularity (minutely, hourly, daily)"
    )
    
    @classmethod
    def from_timeline_entry(
        cls,
        entry: TimelineEntry,
        location_id: int,
        granularity: Literal["minutely", "hourly", "daily"]
    ) -> "WeatherReading":
        """Create a WeatherReading from a TimelineEntry.
        
        Args:
            entry: The timeline entry from the API
            location_id: The database location ID
            granularity: The data granularity
            
        Returns:
            WeatherReading ready for database insertion
        """
        v = entry.values
        return cls(
            location_id=location_id,
            timestamp=entry.time,
            temperature=v.temperature,
            temperature_apparent=v.temperature_apparent,
            wind_speed=v.wind_speed,
            wind_gust=v.wind_gust,
            wind_direction=v.wind_direction,
            humidity=v.humidity,
            precipitation_probability=v.precipitation_probability,
            weather_code=v.weather_code,
            cloud_cover=v.cloud_cover,
            visibility=v.visibility,
            pressure_sea_level=v.pressure_sea_level,
            pressure_surface_level=v.pressure_surface_level,
            dew_point=v.dew_point,
            uv_index=v.uv_index,
            data_granularity=granularity
        )


class LocationSummary(BaseModel):
    """Summary of weather data for a location.
    
    Used for displaying latest readings per location.
    """
    location_id: int
    lat: float
    lon: float
    name: Optional[str]
    timestamp: datetime
    temperature: Optional[float]
    wind_speed: Optional[float]
    humidity: Optional[float]
