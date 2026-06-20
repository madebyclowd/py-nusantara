from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker, declarative_base
from py_nusantara import (
    Nusantara,
    build_models,
    NusantaraSeeder
)

# 1. Setup in-memory SQLite database for demonstration
# (In production, replace this with a PostgreSQL URL e.g. postgresql://user:pass@localhost/db)
DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)
session = SessionLocal()

# 2. Build SQLAlchemy ORM Models dynamically using build_models
Base = declarative_base()
nus = Nusantara()

# Generates {"Province": ProvinceModel, "Regency": RegencyModel, ...}
models = build_models(Base, nus.config)
Province = models["Province"]

# Create tables in the database
Base.metadata.create_all(engine)

# 3. Seed initial CSV datasets into the database tables
print("Seeding core administrative datasets into the database...")
seeder = NusantaraSeeder(session, nus.config, nus.reader)
seeder.seed()
print("Core seeding completed successfully.")

# 4. Bind the database engine to the Nusantara facade
# When bound, all query methods on Nusantara will compile directly to native SQL
# (using PostGIS ST_DWithin/ST_Contains and pg_trgm similarity when on Postgres)
nus.bind(engine)
print("Bound database engine to Nusantara facade.")

print("\n--- 1. Querying bound Database Provinces ---")
# This executes SELECT * FROM provinces ORDER BY name natively
provs = nus.provinces()
print(f"Loaded {len(provs)} provinces from database.")
print(f"First province: {provs[0].name} (ID: {provs[0].id})")

print("\n--- 2. Native SQL Search with Cursor Pagination ---")
# Compiles to SELECT ... FROM ... WHERE name LIKE %Aceh% LIMIT 5
search_res = nus.search("Aceh", limit=5)
if search_res["provinces"]:
    first_id = search_res["provinces"][0].id
    print(f"First search result: {search_res['provinces'][0].name} (ID: {first_id})")

    # Compiles to SELECT ... WHERE name LIKE %Aceh% AND id > :cursor LIMIT 5
    paginated_res = nus.search("Aceh", limit=5, cursor=first_id)
    print("Paginated results after cursor:")
    for p in paginated_res["provinces"]:
        print(f" - {p.name} (ID: {p.id})")

print("\n--- 3. Reverse Geocoding (Native SQL Centroid Math) ---")
# Compiles to SELECT ... ORDER BY distance to centroid point LIMIT 1
lat, lon = 5.54, 95.32
address = nus.find_by_coordinate(lat, lon, fallback_to_nearest=True)
print(f"Resolved hierarchy for coordinates ({lat}, {lon}) via SQL:")
print(f" - Province: {address['province'].name if address['province'] else 'None'}")
print(f" - Regency : {address['regency'].name if address['regency'] else 'None'}")

# Clean up session
session.close()
