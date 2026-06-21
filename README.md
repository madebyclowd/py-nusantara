# Python Nusantara (py-nusantara)

A highly customizable, enterprise-ready, and developer-friendly Python package for Indonesia's administrative regions database (Provinces, Regencies, Districts, and Villages). Compiled according to **Kepmendagri No 300.2.2-2138 Year 2025**.

Designed for both backend integrations (with SQLAlchemy) and **data science environments** (Jupyter Notebooks, Google Colab) with direct, database-free access.

---

## 📚 Documentation Guides

For in-depth guides and production best practices, check out the specialized documentation chapters:
* 🚀 [**Getting Started & Architecture**](docs/getting_started.md) — Installation options, custom schema configuration, dynamic property mapping, and pluggable caches.
* 📊 [**Data Science Guide**](docs/data_science.md) — Exporting to Pandas, Polars, and GeoPandas, performing in-memory 3D KD-Tree spatial KNN/radial/bbox queries, topological borders adjacency matching, and strict NIK century overrides.
* 🧠 [**Backend (Zero-DB Mode)**](docs/backend_zero_db.md) — Deploying high-performance memory-optimized microservices with multi-process Shared Memory (Uvicorn/Gunicorn), asynchronous startup pre-loading, Redis caches, and FastAPI ASGI blueprints.
* 🏛️ [**Backend (DB-Bound Mode)**](docs/backend_db.md) — Integrating SQLAlchemy engines, bulk seeding sync/async streams, native PostGIS compilation (ST_Contains, ST_DWithin), PostgreSQL Trigram fuzzy searches, and Repository design patterns.

---

## ⚡ Key Features

* **Zero-DB Mode**: Load, query, and search regions directly from memory using gzipped CSV datasets—no database connection required.
* **Fuzzy & Scoped Search**: Flexible name lookups with typo correction (Levenshtein, Trigram) and scope constraints (e.g. search within a specific province). Includes helpers like `clean_region_code` and `format_region_code`.
* **Advanced Spatial Queries**: Efficient great-circle distance, radial search, and K-Nearest Neighbors (KNN) using an in-memory 3D KD-Tree, plus bounding box (BBox) viewport queries.
* **Reverse Geocoding**: Resolve `(latitude, longitude)` coordinates directly to Province, Regency, District, and Village hierarchies using point-in-polygon boundary matching with Haversine distance fallback.
* **Historical Regional Mapping**: Transparent handling of legacy codes and historical splits (e.g. Papua province splits), supporting lookup methods and NIK processing from older datasets.
* **GIS Boundaries & GeoJSON**: Download high-resolution geographic boundaries on-demand, convert boundaries to WKT, or export records directly to standard GeoJSON features using `.to_geojson()`.
* **Official Regional Logos**: Retrieve CDN-hosted official regional emblem (lambang daerah) WebP URLs for all provinces and regencies directly from record wrappers.
* **Data Science Ready**: Convert records directly to Pandas or Polars DataFrames using simple helpers (e.g. `provinces_df()`).
* **Complete Schema Freedom**: Custom table names and column renames matching your corporate schema guidelines.
* **Dynamic Property Accessors**: Intercepts attribute calls to logically mapped names (e.g. access `province.name` even if configured as `nama_provinsi` in your database).
* **Pluggable Caching**: Built-in TTL caching (InMemoryCache) with optional Redis support to minimize file parsing or database query overhead.
* **Low-Memory Seeder**: Streams datasets and seeds databases in bulk chunks (e.g., SQLite, PostgreSQL, MySQL, SQL Server) using SQLAlchemy, supporting both synchronous and asynchronous operations.

---

## 📦 Installation

Install the package via `pip` or `uv`:

```bash
# Core package (Database-free direct queries only)
uv add py-nusantara

# For Pandas Dataframe exports
uv add py-nusantara --optional pandas

# For SQL databases (SQLAlchemy models and seeding)
uv add py-nusantara --optional sqlalchemy

# For Redis query caching
uv add py-nusantara --optional redis

# Install everything
uv add py-nusantara --optional pandas --optional sqlalchemy --optional redis
```

---

## 🗺️ Direct Data Access (Jupyter / Google Colab)

No database is required to browse, query, and traverse administrative records.

```python
import py_nusantara as nus

# 1. Fetch all Provinces
provinces = nus.provinces()  # returns list of ProvinceRecord
print(f"Total Provinces: {len(provinces)}")

# 2. Get specific Province by ID
province = nus.find_province("11")  # Aceh
print(f"Capital: {province.capital}")

# 3. Traverse relations (Province -> Regencies -> Districts -> Villages)
regencies = province.regencies
first_regency = regencies[0]
print(f"Regency Name: {first_regency.name}")

# 4. Search regions dynamically across all levels
results = nus.search("Bakongan")
# Returns: {"provinces": [], "regencies": [], "districts": [...], "villages": [...]}
```

---

## 🔍 Fuzzy & Scoped Search

Search for administrative divisions dynamically with typo correction and parent constraints:

```python
import py_nusantara as nus

# 1. Fuzzy Search to correct typos (e.g. "Makasar" -> "Kota Makassar")
res_fuzzy = nus.search("Makasar", fuzzy=True, threshold=0.7, similarity_method="levenshtein")
# Methods supported: "levenshtein" and "trigram"

# 2. Scoped Search: Search "Bakongan" but only within Aceh (Province ID "11")
res_scoped = nus.search("Bakongan", scope={"province_id": "11"})

# 3. Clean and format regional codes dynamically
cleaned = nus.clean_region_code("32.73.01.2001") # "3273012001"
formatted = nus.format_region_code("3273012001") # "32.73.01.2001"
is_valid = nus.validate_region_code("32.73.01.2001") # True
```

---

## 📍 Reverse Geocoding & Spatial Queries

Resolve any `(latitude, longitude)` coordinate into the corresponding administrative hierarchy. You can also run spatial queries using the package's in-memory 3D KD-Tree:

```python
import py_nusantara as nus

# 1. Resolve containing regions (falls back to nearest centroids by default)
regions = nus.find_by_coordinate(latitude=-6.1751, longitude=106.8650)

# 2. K-Nearest Neighbors (KNN) Spatial Search
# Find the 3 nearest provinces to a coordinate
nearest_provs = nus.find_knn(5.54, 95.32, k=3, level="provinces")

# 3. Radial Nearby Search
# Find all districts within 50 km of a coordinate
nearby_districts = nus.find_nearby(5.54, 95.32, radius_km=50.0, level="districts")

# 4. Bounding Box (BBox) Query
# Find all provinces inside or intersecting a bounding box
bbox_provs = nus.find_in_bbox(min_lat=2.0, min_lon=95.0, max_lat=6.0, max_lon=98.0, level="provinces")

# 5. Distance between two administrative entities in kilometers
prov1 = nus.find_province("11") # Aceh
prov2 = nus.find_province("12") # Sumatera Utara
distance = prov1.distance_to(prov2)
```

---

## 📊 Pandas Data Science Integration

Export regions straight into Pandas DataFrames for quick data manipulation or visualization.

```python
import py_nusantara as nus

# Convert provinces to Pandas DataFrame
df_provinces = nus.provinces_df()

# Get regencies as DataFrame
df_regencies = nus.regencies_df(province_id="11")
```

---

## 📜 Historical Mapping & NIK Parsing

Transparently resolve obsolete/legacy regional IDs (from historical Splits) and parse legacy NIK numbers:

```python
import py_nusantara as nus

# 1. Historical split mapping
# Merauke old code "9101" maps to active "9301" in Papua Selatan
active_id = nus.resolve_legacy_id("9101") # "9301"

# Lookups automatically resolve legacy IDs
merauke = nus.find_regency("9101")
print(merauke.id) # "9301"

# 2. Parsing a NIK (including legacy codes)
nik_info = nus.parse_nik("9101010402020001")
print(nik_info.province.name) # "Papua Selatan" (Correctly mapped to active ID "93")
```

---

## 🌐 On-Demand Geographic Boundaries & GeoJSON

By default, boundary coordinate data is excluded to keep the package lightweight. When needed, they can be downloaded and cached locally, or exported to GeoJSON:

```python
import py_nusantara as nus

# 1. Enable boundary columns in configuration
nus.init({
    "columns": {
        "provinces": {"boundary": {"enabled": True}}
    }
})

# 2. Download and verify boundaries checksums (stored in ~/.cache/py-nusantara/)
nus.download_boundaries(levels="provinces")

# 3. Access coordinates directly in memory or dataframe
aceh = nus.find_province("11")

# 4. Format JSON to WKT (Well-Known Text) for spatial engines
wkt = nus.json_to_wkt(aceh.boundary)

# 5. Export record to standard GeoJSON Feature dictionary
geojson_feat = aceh.to_geojson()
```

---

## 🏛️ Regional Logos (Emblems)

Retrieve CDN URLs pointing to official regional logos/emblems (`.webp` format) for provinces and regencies. By default, logos are enabled and point to the custom domain CDN, but they can be custom configured or disabled:

```python
import py_nusantara as nus

# 1. Access province logo URL
aceh = nus.find_province("11")
print(aceh.logo_url)  # "https://data.clowdlab.com/nusantara/logos/provinces/11.webp"

# 2. Access regency logo URL
aceh_barat = nus.find_regency("1101")
print(aceh_barat.logo_url)  # "https://data.clowdlab.com/nusantara/logos/regencies/1101.webp"

# 3. Dynamic fields are automatically serialized in to_dict()
print(aceh.to_dict())  # Includes 'logo_url' key

# Note: Districts and Villages do not have regional logos (returns None)
district = nus.find_district("110101")
print(district.logo_url)  # None

# 4. Disable or customize base CDN URL in configuration
nus.init({
    "logo": {
        "enabled": False,  # Turn off logo_url generation (will return None)
        "base_url": "https://your-custom-cdn.com/logos"  # Override CDN URL host
    }
})
```

---

## 🏛️ Database Integration & Seeding (SQLAlchemy)

Create tables and bulk seed administrative data into your database, supporting both synchronous and asynchronous connections:

### Synchronous Seeding
```python
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
import py_nusantara as nus

engine = create_engine("sqlite:///nusantara.db")
Session = sessionmaker(bind=engine)
session = Session()

Base = declarative_base()
models = nus.build_models(Base, nus.Nusantara().config)

Base.metadata.create_all(engine)

# Seed core datasets and boundaries
seeder = nus.NusantaraSeeder(session, nus.Nusantara().config, nus.Nusantara().reader)
seeder.seed()
seeder.seed_boundaries(levels=["provinces"])
```

### Asynchronous Seeding (using sqlalchemy.ext.asyncio)
```python
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import declarative_base
import py_nusantara as nus

engine = create_async_engine("postgresql+asyncpg://user:pass@localhost/dbname")
async_session = AsyncSession(engine)

Base = declarative_base()
models = nus.build_models(Base, nus.Nusantara().config)

# Run migrations and seed data asynchronously
async def main():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
    seeder = nus.NusantaraSeeder(async_session, nus.Nusantara().config, nus.Nusantara().reader)
    await seeder.seed_async()
    await seeder.seed_boundaries_async(levels=["provinces"])
```

---

## ⚙️ Configuration

Initialize `Nusantara` with custom configuration structures:

```python
custom_config = {
    "tables": {
        "provinces": "indonesia_provinces",  # custom table name
    },
    "columns": {
        "provinces": {
            "name": {"name": "nama_provinsi", "enabled": True},  # renamed
            "timezone": {"enabled": False},  # excluded
        }
    },
    "cache": {
        "enabled": True,
        "ttl": 86400,
        "prefix": "nusantara",
        "redis_url": "redis://localhost:6379/0",  # redis caching
    }
}

nus = nus.init(custom_config)
```

---

## 🧪 Testing

To run the test suite:

```bash
uv run pytest
```

---

## 🤝 Credits

* Special thanks to [cahyadsn](https://github.com/cahyadsn) for curating and providing the raw Indonesia administrative data used as the source for this package's dataset.

---

## 📄 License

The MIT License (MIT). Please see [LICENSE](LICENSE) for more information.
