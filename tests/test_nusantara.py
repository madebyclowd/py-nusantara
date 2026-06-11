import pytest
import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from py_nusantara import (
    Nusantara,
    provinces,
    find_province,
    regencies_of,
    find_regency,
    districts_of,
    find_district,
    villages_of,
    find_village,
    search,
    clear_cache,
    provinces_df,
    ConfigurationError,
    IntegrityError,
    build_models,
    NusantaraSeeder,
    json_to_wkt,
)


def test_default_facade_direct_access():
    """Test standard direct CSV reading through default facade functions."""
    # Fetch provinces
    provs = provinces()
    assert len(provs) > 0
    
    # Verify a specific province (Aceh ID = '11')
    aceh = find_province("11")
    assert aceh is not None
    assert aceh.name == "Aceh"
    assert aceh.capital == "Banda Aceh"

    # Fetch regencies of Aceh
    regencies = regencies_of("11")
    assert len(regencies) > 0
    # First regency: Kabupaten Aceh Selatan (ID = '1101')
    simeulue = find_regency("1101")
    assert simeulue is not None
    assert simeulue.name == "Kabupaten Aceh Selatan"
    assert simeulue.province_id == "11"
    assert simeulue.province.id == "11"

    # Fetch districts of Simeulue
    districts = districts_of("1101")
    assert len(districts) > 0
    # First district: Bakongan (ID = '110101')
    teupah_selatan = find_district("110101")
    assert teupah_selatan is not None
    assert teupah_selatan.name == "Bakongan"
    assert teupah_selatan.regency_id == "1101"
    assert teupah_selatan.regency.id == "1101"

    # Fetch villages of Teupah Selatan (Lazy loading check)
    villages = villages_of("110101")
    assert len(villages) > 0
    # A village: Keude Bakongan (ID = '1101012001')
    lanting = find_village("1101012001")
    assert lanting is not None
    assert lanting.name == "Keude Bakongan"
    assert lanting.district_id == "110101"
    assert lanting.district.id == "110101"


def test_custom_column_mapping_and_exclusions():
    """Test custom configuration with column renaming and column exclusions."""
    custom_cfg = {
        "tables": {
            "provinces": "custom_provinces",
        },
        "columns": {
            "provinces": {
                "name": {"name": "nama_provinsi", "enabled": True},
                "capital": {"name": "ibu_kota", "enabled": True},
                "timezone": {"name": "timezone", "enabled": False},  # Excluded
            }
        }
    }
    
    nus = Nusantara(custom_cfg)
    provs = nus.provinces()
    assert len(provs) > 0
    
    aceh = nus.find_province("11")
    assert aceh is not None
    
    # Check that we can access using standard logical names (transparent mapping)
    assert aceh.name == "Aceh"
    assert aceh.capital == "Banda Aceh"

    # Direct database mapping names should work
    assert aceh._data["nama_provinsi"] == "Aceh"
    assert aceh._data["ibu_kota"] == "Banda Aceh"

    # Accessing timezone should raise AttributeError because it is disabled
    with pytest.raises(AttributeError, match="is disabled in configuration"):
        _ = aceh.timezone


def test_invalid_configuration_keys():
    """Ensure configuring primary or foreign keys to be disabled raises ConfigurationError."""
    bad_cfg = {
        "columns": {
            "provinces": {
                "id": {"name": "id", "enabled": False}  # Primary key must be enabled
            }
        }
    }
    with pytest.raises(ConfigurationError):
        Nusantara(bad_cfg)


def test_search():
    """Test case-insensitive substring searching across all levels."""
    clear_cache()
    # Search for "Bakongan"
    results = search("Bakongan")
    
    # Should find matching districts / villages
    assert len(results["districts"]) > 0 or len(results["villages"]) > 0
    for key in ["provinces", "regencies", "districts", "villages"]:
        assert isinstance(results[key], list)


def test_dataframe_integration():
    """Test that data science helper methods return proper pandas DataFrames."""
    df = provinces_df()
    assert isinstance(df, pd.DataFrame)
    assert "id" in df.columns
    assert "name" in df.columns
    assert len(df) > 0


def test_sqlalchemy_and_seeder():
    """Test SQLAlchemy model builder factory and the seeder in SQLite."""
    # Create an in-memory SQLite database
    engine = create_engine("sqlite:///:memory:")
    Session = sessionmaker(bind=engine)
    session = Session()

    Base = declarative_base()
    config = Nusantara().config

    # Generate models dynamically
    models = build_models(Base, config)
    assert "Province" in models
    assert "Regency" in models
    assert "District" in models
    assert "Village" in models

    # Create tables in memory
    Base.metadata.create_all(engine)

    # Seed the database using our seeder
    reader = Nusantara().reader
    seeder = NusantaraSeeder(session, config, reader)
    seeder.seed()

    # Query database to verify it seeded correctly
    db_provinces = session.query(models["Province"]).all()
    assert len(db_provinces) > 0

    aceh = session.query(models["Province"]).filter_by(id="11").first()
    assert aceh is not None
    assert aceh.name == "Aceh"
    
    # Test relationship
    assert len(aceh.regencies) > 0
    assert len(aceh.districts) > 0

    session.close()


def test_json_to_wkt():
    """Test JSON to WKT coordinate conversions for Polygons and MultiPolygons."""
    # Test Polygon conversion
    poly_json = "[[[0, 10], [0, 20], [10, 20], [10, 10], [0, 10]]]"
    wkt = json_to_wkt(poly_json)
    assert wkt == "POLYGON((10 0, 20 0, 20 10, 10 10, 10 0))"

    # Test MultiPolygon conversion
    multipoly_json = "[[[[0, 10], [0, 20], [10, 20], [10, 10], [0, 10]]], [[[30, 40], [30, 50], [40, 50], [30, 40]]]]"
    wkt = json_to_wkt(multipoly_json)
    assert wkt == "MULTIPOLYGON(((10 0, 20 0, 20 10, 10 10, 10 0)), ((40 30, 50 30, 50 40, 40 30)))"

    # Test degenerate/malformed cases
    assert json_to_wkt("") is None
    assert json_to_wkt("invalid json") is None
    assert json_to_wkt("[]") is None


def test_boundary_integration(tmp_path):
    """Test boundary loading from a mock cache folder and seeding into database."""
    import gzip
    import csv
    import hashlib
    from py_nusantara.manifest import Manifest
    
    mock_file = tmp_path / "provinces.csv.gz"
    
    headers = ["id", "name", "capital", "latitude", "longitude", "elevation", "timezone", "area", "population", "boundary"]
    rows = [
        ["11", "Aceh", "Banda Aceh", "5.5", "95.3", "12.0", "WIB", "56789.0", "5000000", "[[[5.5, 95.3], [5.6, 95.4], [5.5, 95.4], [5.5, 95.3]]]"]
    ]
    
    with gzip.open(mock_file, "wt", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)
        
    # Get hash of the mock file and override Manifest hash dynamically for testing
    sha = hashlib.sha256()
    with open(mock_file, "rb") as f:
        while chunk := f.read(8192):
            sha.update(chunk)
    mock_hash = sha.hexdigest()
    
    Manifest.HASHES["provinces.csv.gz"] = mock_hash
    
    # Configure Nusantara to use our mock cache directory and enable boundary column
    config_dict = {
        "columns": {
            "provinces": {
                "boundary": {"name": "boundary", "enabled": True}
            }
        },
        "boundaries": {
            "local_path": str(tmp_path),
            "type": "spatial"
        }
    }
    
    nus = Nusantara(config_dict)
    
    # Test 1: Reader loads boundaries from mock cache file
    provs = nus.provinces()
    assert len(provs) == 1
    assert provs[0].name == "Aceh"
    # Ensure boundary is readable
    assert provs[0].boundary == "[[[5.5, 95.3], [5.6, 95.4], [5.5, 95.4], [5.5, 95.3]]]"
    
    # Test 2: Database seeding of spatial boundaries
    engine = create_engine("sqlite:///:memory:")
    
    from sqlalchemy import event
    @event.listens_for(engine, "connect")
    def register_functions(dbapi_connection, connection_record):
        dbapi_connection.create_function("ST_GeomFromText", 1, lambda val: f"SPATIAL:{val}")

    Session = sessionmaker(bind=engine)
    session = Session()

    Base = declarative_base()
    models = build_models(Base, nus.config)
    Base.metadata.create_all(engine)
    
    # Run seeder for core data
    seeder = NusantaraSeeder(session, nus.config, nus.reader)
    seeder.seed()
    
    # Seed boundaries from mock cache file, force=True to overwrite raw JSON default seed
    seeder.seed_boundaries(levels=["provinces"], force=True, cache_dir=str(tmp_path))
    
    # Verify spatial WKT was written to the boundary column
    db_prov = session.query(models["Province"]).filter_by(id="11").first()
    assert db_prov is not None
    assert db_prov.boundary == "SPATIAL:POLYGON((95.3 5.5, 95.4 5.6, 95.4 5.5, 95.3 5.5))"
    
    session.close()
