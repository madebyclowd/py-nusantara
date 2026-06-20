# Data Science Integration and Spatial Analysis

`py-nusantara` is built with first-class support for spatial data science, data visualization, and demographic analysis. It integrates seamlessly with **Pandas**, **Polars**, and **GeoPandas**.

---

## 📊 Tabular Dataframes (Pandas & Polars)

You can convert any regional lists directly into Pandas or Polars DataFrames. This is highly useful for grouping, sorting, or plotting charts in Jupyter Notebooks or Google Colab.

### 1. Pandas Integration

Ensure you have installed the optional group:
```bash
uv add py-nusantara --optional pandas
```

Get dataframes for any administrative level:
```python
import py_nusantara as nus

# Load all provinces as a Pandas DataFrame
df_provinces = nus.provinces_df()
print(df_provinces.head())

# Load regencies within a specific province (e.g., West Java "32")
df_regencies = nus.regencies_df(province_id="32")
print(df_regencies[["id", "name", "latitude", "longitude"]])
```

### 2. Polars Integration

If you prefer Polars for faster, multi-threaded dataframe processing:
```python
import polars as pl
import py_nusantara as nus

# Convert records directly to Polars DataFrame
provinces = nus.provinces()
df_provinces = pl.DataFrame([p.to_dict() for p in provinces])
print(df_provinces.select(["id", "name"]))
```

---

## 🗺️ GeoPandas & GIS Spatial Dataframes

For advanced spatial analyses (such as spatial joins, buffer queries, and map plotting), you can export administrative records to a **GeoPandas GeoDataFrame**. This converts the boundary polygons into dedicated **Shapely** geometry objects.

```python
import py_nusantara as nus
from py_nusantara import to_geodataframe

# Enable boundary coordinate columns in configuration
nus.init({
    "columns": {
        "provinces": {"boundary": {"enabled": True}}
    }
})

# Make sure coordinate boundary files are downloaded locally
nus.download_boundaries(levels="provinces")

# Retrieve records
provinces = nus.provinces()

# Convert list of ProvinceRecord to GeoDataFrame
gdf = to_geodataframe(provinces)

# The resulting GeoDataFrame has a 'geometry' column populated with Shapely Polygons/MultiPolygons
print(gdf[["id", "name", "geometry"]].head())

# Plot the map using matplotlib
gdf.plot(column="name", cmap="plasma", figsize=(12, 6))
```

---

## 🔍 In-Memory Spatial Queries

`py-nusantara` comes pre-packed with a **3D KD-Tree** spatial index (mapping latitude, longitude, and height/radius coordinates). This index allows you to query regions using geometry math without requiring a spatial database.

### 1. K-Nearest Neighbors (KNN)
Find the closest $K$ administrative entities to a given coordinate:

```python
import py_nusantara as nus

# Find the 5 nearest regencies to Banda Aceh
nearest_regencies = nus.find_knn(
    latitude=5.54, 
    longitude=95.32, 
    k=5, 
    level="regencies"
)

for regency in nearest_regencies:
    print(f"{regency.name} (Distance: {regency.distance_to(5.54, 95.32):.2f} km)")
```

### 2. Radial (Nearby) Search
Find all administrative entities within a specific circular radius (in kilometers) from a coordinate:

```python
import py_nusantara as nus

# Find all districts within 30 km of Jakarta (Monas)
nearby_districts = nus.find_nearby(
    latitude=-6.1751, 
    longitude=106.8650, 
    radius_km=30.0, 
    level="districts"
)
```

### 3. Bounding Box Viewport Queries
Query all entities inside or intersecting a bounding box envelope. The bounding box wraps correctly around the **180°/-180° antimeridian longitude**:

```python
import py_nusantara as nus

# Viewport search across the antimeridian line
bbox_regions = nus.find_in_bbox(
    min_lat=2.0, 
    min_lon=179.0, 
    max_lat=6.0, 
    max_lon=-179.0, 
    level="provinces"
)
```

---

## 🧩 Topological Adjacency Queries

When performing spatial analysis, you often need to find neighboring regions that share physical borders. The `find_adjacent()` method performs topology checks using **Shapely's `.touches()`** operator:

```python
import py_nusantara as nus
from py_nusantara import find_adjacent

# Enable boundaries
nus.init({
    "columns": {"provinces": {"boundary": {"enabled": True}}}
})
nus.download_boundaries(levels="provinces")

# Retrieve West Java
west_java = nus.find_province("32")

# Find all adjacent provinces
neighbors = find_adjacent(west_java, level="provinces")
for n in neighbors:
    print(f"Adjacent Province: {n.name} (ID: {n.id})")
    # Output will include DKI Jakarta ("31") and Banten ("36")
```

---

## 🪪 NIK Parsing & Century Overrides

Indonesia's National Identity Card number (Nomor Induk Kependudukan - NIK) encodes regional origin, gender, and date of birth. 

By default, the NIK parser uses a floating heuristic to resolve birth years (assuming years matching future dates belong to the 1900s). For elderly demographics, this can cause data collisions. To solve this, enforce a **strict century override**:

```python
import py_nusantara as nus

# Normal parsing uses the heuristic:
nik_heuristic = nus.parse_nik("1101010101400001") # Birthday YY is "40"
print(nik_heuristic.birth_date) # 1940-01-01 (by heuristic)

# If parsing a modern record where the person was born in 2040:
nik_strict = nus.parse_nik("1101010101400001", century_override=2000)
print(nik_strict.birth_date) # 2040-01-01 (deterministic override)

# Validate NIK with a strict century constraint
is_valid = nus.validate_nik("1101010101400001", century_override=1900)
```
