# Python Nusantara (py-nusantara)

A highly customizable, enterprise-ready, and developer-friendly Python package for Indonesia's administrative regions database (Provinces, Regencies, Districts, and Villages). Compiled according to **Kepmendagri No 300.2.2-2138 Year 2025**.

Designed for both backend backend integrations (with SQLAlchemy) and **data science environments** (Jupyter Notebooks, Google Colab) with direct, database-free access.

---

## ⚡ Key Features

* **Zero-DB Mode**: Load, query, and search regions directly from memory using gzipped CSV datasets—no database connection required.
* **On-Demand Boundaries (GIS)**: Keep the package size tiny. High-resolution geographic boundary coordinates (polygons/multipolygons) are downloaded only when you ask for them.
* **Data Science Ready**: Convert records directly to Pandas or Polars DataFrames using simple helpers (e.g. `provinces_df()`).
* **Complete Schema Freedom**: Custom table names and column renames matching your corporate schema guidelines.
* **Dynamic Property Accessors**: Intercepts attribute calls to logically mapped names (e.g. access `province.name` even if configured as `nama_provinsi` in your database).
* **Pluggable Caching**: Built-in TTL caching (InMemoryCache) with optional Redis support to minimize file parsing or database query overhead.
* **Low-Memory Seeder**: Streams datasets and seeds databases in bulk chunks (e.g., SQLite, PostgreSQL, MySQL, SQL Server) using SQLAlchemy.

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

districts = first_regency.districts
first_district = districts[0]

villages = first_district.villages
if villages:
    first_village = villages[0]
    print(f"Village: {first_village.name} (Postal: {first_village.postal_code})")

# 4. Search regions dynamically across all levels
results = nus.search("Bakongan")
# Returns: {"provinces": [], "regencies": [], "districts": [...], "villages": [...]}
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

## 🌐 On-Demand Geographic Boundaries (GIS)

By default, boundary coordinate data is excluded to keep the package lightweight. When needed, they can be downloaded and cached locally.

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
print(aceh.boundary) # Raw JSON coordinate array

# 4. Format JSON to WKT (Well-Known Text) for spatial engines
wkt = nus.json_to_wkt(aceh.boundary)
print(wkt) # e.g. "POLYGON((95.3 5.5, ...))"
```

---

## 🏛️ Database Integration & Seeding (SQLAlchemy)

Create tables and bulk seed administrative data into your SQLAlchemy-supported database:

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
import py_nusantara as nus

# 1. Setup SQLAlchemy Connection
engine = create_engine("sqlite:///nusantara.db")
Session = sessionmaker(bind=engine)
session = Session()

Base = declarative_base()

# 2. Build Models dynamically matching your configuration
models = nus.build_models(Base, nus.Nusantara().config)
# Generates ORM classes: models["Province"], models["Regency"], models["District"], models["Village"]

# 3. Create tables in Database
Base.metadata.create_all(engine)

# 4. Seed core datasets (Streams gzipped files in chunks under 2MB memory)
seeder = nus.NusantaraSeeder(session, nus.Nusantara().config, nus.Nusantara().reader)
seeder.seed()

# 5. Seed boundaries (Optional, run download_boundaries first)
seeder.seed_boundaries(levels=["provinces", "regencies"])
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

## 📄 License

The MIT License (MIT). Please see [LICENSE](LICENSE) for more information.
