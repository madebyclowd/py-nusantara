# Backend Development (DB-Bound Mode)

For large-scale enterprise applications, running administrative queries in-memory is not always feasible. High-volume searches, coordinate matching, and complex joins are best offloaded to a relational database like **PostgreSQL** with **PostGIS** spatial capabilities.

`py-nusantara` supports database integration using **SQLAlchemy** (supporting both synchronous and asynchronous operations). This guide explains how to set up, seed, and query administrative data using your database.

---

## 🏗️ SQLAlchemy Integration

`py-nusantara` provides a model builder that dynamically constructs SQLAlchemy models based on your custom table and column configurations.

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base
from py_nusantara import Nusantara, build_models

# 1. Setup connection
DATABASE_URL = "postgresql://user:pass@localhost/dbname"
engine = create_engine(DATABASE_URL)

# 2. Build Models Dynamically
Base = declarative_base()
nus = Nusantara()

# Generates mapped ORM classes matching config names
models = build_models(Base, nus.config)
Province = models["Province"]
Regency = models["Regency"]
District = models["District"]
Village = models["Village"]

# Create tables in the database (if running migrations manually)
Base.metadata.create_all(engine)
```

---

## 🌾 Seeding Data

Seeding administrative reference tables can be done synchronously or asynchronously. The seeder streams raw data in bulk chunks, making it extremely memory-efficient.

### 1. Synchronous Seeding
```python
from sqlalchemy.orm import sessionmaker
from py_nusantara import NusantaraSeeder

Session = sessionmaker(bind=engine)
with Session() as session:
    seeder = NusantaraSeeder(session, nus.config, nus.reader)
    
    # Seeds core regional tables
    seeder.seed()
    
    # Seeds optional GIS boundaries (e.g. for Province level)
    seeder.seed_boundaries(levels=["provinces"])
```

### 2. Asynchronous Seeding (FastAPI/asyncpg)
Using SQLAlchemy's `ext.asyncio` extension:

```python
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from py_nusantara import NusantaraSeeder

async_engine = create_async_engine("postgresql+asyncpg://user:pass@localhost/dbname")

async def run_seeder():
    async with AsyncSession(async_engine) as session:
        seeder = NusantaraSeeder(session, nus.config, nus.reader)
        
        # Async seeding
        await seeder.seed_async()
        await seeder.seed_boundaries_async(levels=["provinces"])
```

---

## 🔗 Binding the Database Engine

Once your database is seeded, bind the engine to the `Nusantara` facade:

```python
# Bind the SQLAlchemy engine
nus.bind(engine)
```

> [!IMPORTANT]
> Once `nus.bind(engine)` is executed, the `InMemoryQueryAdapter` is swapped with a `DatabaseQueryAdapter`. Calling facade search or spatial methods will compile directly to native SQL queries executed on your database, rather than querying in-process memory.

---

## ⚡ Native SQL Compilations (PostGIS & pg_trgm)

The database adapter automatically compiles Python spatial query methods into optimized, native SQL. 

### 1. Reverse Geocoding (`find_by_coordinate`)
Compiles to native **PostGIS point-in-polygon** checks:
- **SQL Equivalent**:
  ```sql
  SELECT * FROM ref_provinces 
  WHERE ST_Contains(ref_provinces.boundary, ST_SetSRID(ST_Point(lon, lat), 4326))
  LIMIT 1;
  ```

### 2. Radial & Nearby queries (`find_nearby`)
Uses PostGIS distance operators for distance searches in meters:
- **SQL Equivalent**:
  ```sql
  SELECT * FROM ref_districts
  WHERE ST_DWithin(
      ref_districts.boundary, 
      ST_SetSRID(ST_Point(lon, lat), 4326)::geography, 
      radius_km * 1000
  );
  ```

### 3. Autocomplete Fuzzy Search (`search`)
Uses PostgreSQL trigram matching (if `pg_trgm` extension is enabled) or `ILIKE` fallback for fast typing matching:
- **SQL Equivalent**:
  ```sql
  SELECT * FROM ref_regencies
  WHERE name ILIKE '%Makasar%' OR similarity(name, 'Makasar') > 0.3
  ORDER BY similarity(name, 'Makasar') DESC
  LIMIT 5;
  ```

---

## 🏛️ Repository-Service-Controller Design Pattern

In production enterprise architectures, wrap the `Nusantara` database-bound facade inside repositories to maintain clean separations of concerns.

```python
# repositories/regional_repository.py
from typing import List, Optional
from sqlalchemy.orm import Session
from py_nusantara import Nusantara

class RegionalRepository:
    def __init__(self, db_session: Session):
        self.session = db_session
        self.nus = Nusantara()
        # The facade uses the bound database queries
        
    def find_provinces(self) -> List:
        return self.nus.provinces()
        
    def autocomplete_search(self, query: str, limit: int = 5, cursor: Optional[str] = None) -> dict:
        return self.nus.search(query, limit=limit, cursor=cursor)

# services/address_service.py
class AddressService:
    def __init__(self, repository: RegionalRepository):
        self.repository = repository
        
    def get_suggestions(self, user_input: str) -> List[dict]:
        raw_res = self.repository.autocomplete_search(user_input, limit=5)
        # Apply business rules or mapping
        suggestions = []
        for level, records in raw_res.items():
            for r in records:
                suggestions.append({
                    "label": f"{r.name} ({level[:-1].capitalize()})",
                    "code": r.id
                })
        return suggestions
```
This keeps your domain logic completely separate from physical SQL queries.
