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
    NIKValidationError,
    NIKInfo,
    parse_nik,
    validate_nik,
    PostalCodeValidationError,
    PostalCodeInfo,
    parse_postal_code,
    validate_postal_code,
    clean_region_code,
    format_region_code,
    validate_region_code,
    find_nearby,
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


def test_singleton_thread_safety():
    import py_nusantara
    from concurrent.futures import ThreadPoolExecutor
    py_nusantara._global_instance = None # reset
    
    def get_facade():
        return py_nusantara._get_instance()
        
    with ThreadPoolExecutor(max_workers=10) as executor:
        instances = list(executor.map(lambda _: get_facade(), range(20)))
        
    first_id = id(instances[0])
    for inst in instances:
        assert id(inst) == first_id


def test_path_traversal_detection():
    nus = Nusantara()
    with pytest.raises(ValueError, match="Directory traversal attempt detected"):
        nus.reader._get_file_path("../../unsafe.csv.gz")


def test_verify_checksum_disabled(tmp_path):
    import gzip
    import csv
    
    # Create mock provinces.csv.gz file (its hash won't match manifest)
    mock_file = tmp_path / "provinces.csv.gz"
    headers = ["id", "name", "capital", "latitude", "longitude", "elevation", "timezone", "area", "population", "boundary"]
    rows = [["11", "Aceh", "Banda Aceh", "5.5", "95.3", "12.0", "WIB", "56789.0", "5000000", ""]]
    with gzip.open(mock_file, "wt", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)
        
    # verify_checksum: False
    config_dict = {
        "boundaries": {
            "local_path": str(tmp_path),
            "verify_checksum": False
        }
    }
    
    nus = Nusantara(config_dict)
    # This should succeed without raising IntegrityError because verify_checksum is False
    provs = nus.provinces()
    assert len(provs) == 1
    assert provs[0].name == "Aceh"


def test_redis_cache_scoped_clear(monkeypatch):
    from py_nusantara.cache import RedisCache
    
    class MockRedisClient:
        def __init__(self):
            self.keys = ["nusantara.key1", "nusantara.key2", "other.key3"]
        def scan_iter(self, match):
            pattern = match.replace("*", "")
            return [k for k in self.keys if k.startswith(pattern)]
        def delete(self, *keys):
            for k in keys:
                if k in self.keys:
                    self.keys.remove(k)
        def flushdb(self):
            self.keys.clear()
            
    # Mock redis module
    import sys
    from types import ModuleType
    mock_redis_module = ModuleType("redis")
    mock_redis_module.from_url = lambda url, **kwargs: MockRedisClient()
    sys.modules["redis"] = mock_redis_module
    
    # Test with prefix
    cache = RedisCache("redis://localhost:6379", prefix="nusantara")
    assert len(cache._client.keys) == 3
    cache.clear()
    assert "nusantara.key1" not in cache._client.keys
    assert "nusantara.key2" not in cache._client.keys
    assert "other.key3" in cache._client.keys # should not be deleted
    
    # Test without prefix
    cache_no_prefix = RedisCache("redis://localhost:6379")
    cache_no_prefix.clear()
    assert len(cache_no_prefix._client.keys) == 0 # everything deleted


def test_find_by_coordinate_centroid_fallback():
    # Use real core dataset centroids
    # Aceh: lat=5.53, lon=95.32
    from py_nusantara import find_by_coordinate
    res = find_by_coordinate(5.5, 95.3, fallback_to_nearest=True)
    
    # It should fallback to the nearest centroid since boundaries are not loaded/present
    assert res["province"] is not None
    assert res["province"].name == "Aceh"
    assert res["regency"] is not None
    assert res["district"] is not None
    assert res["village"] is not None


def test_find_by_coordinate_no_fallback():
    from py_nusantara import find_by_coordinate
    # If fallback is False and no boundary files exist, all should be None
    res = find_by_coordinate(5.5, 95.3, fallback_to_nearest=False)
    assert res["province"] is None
    assert res["regency"] is None
    assert res["district"] is None
    assert res["village"] is None


def test_find_by_coordinate_exact_boundary(tmp_path):
    import gzip
    import csv
    from py_nusantara import Nusantara
    
    # Create mock cache files containing boundaries
    mock_prov = tmp_path / "provinces.csv.gz"
    headers = ["id", "name", "capital", "latitude", "longitude", "elevation", "timezone", "area", "population", "boundary"]
    rows = [["11", "Aceh", "Banda Aceh", "5.5", "95.3", "12.0", "WIB", "56789.0", "5000000", "[[[5.0, 95.0], [6.0, 95.0], [6.0, 96.0], [5.0, 96.0], [5.0, 95.0]]]"]]
    with gzip.open(mock_prov, "wt", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)

    mock_reg = tmp_path / "regencies.csv.gz"
    headers_reg = ["id", "province_id", "name", "capital", "latitude", "longitude", "elevation", "timezone", "area", "population", "boundary"]
    rows_reg = [["1101", "11", "Kabupaten Aceh Selatan", "Tapak Tuan", "3.2", "97.2", "15.0", "WIB", "4000.0", "200000", "[[[5.1, 95.1], [5.9, 95.1], [5.9, 95.9], [5.1, 95.9], [5.1, 95.1]]]"]]
    with gzip.open(mock_reg, "wt", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers_reg)
        writer.writerows(rows_reg)

    mock_dist = tmp_path / "districts.csv.gz"
    headers_dist = ["id", "regency_id", "name", "latitude", "longitude", "boundary"]
    rows_dist = [["110101", "1101", "Bakongan", "3.0", "97.4", "[[[5.2, 95.2], [5.8, 95.2], [5.8, 95.8], [5.2, 95.8], [5.2, 95.2]]]"]]
    with gzip.open(mock_dist, "wt", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers_dist)
        writer.writerows(rows_dist)

    mock_vil = tmp_path / "villages_11.csv.gz"
    headers_vil = ["id", "district_id", "name", "postal_code", "latitude", "longitude", "boundary"]
    rows_vil = [["1101012001", "110101", "Keude Bakongan", "23773", "3.0", "97.4", "[[[5.3, 95.3], [5.7, 95.3], [5.7, 95.7], [5.3, 95.7], [5.3, 95.3]]]"]]
    with gzip.open(mock_vil, "wt", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers_vil)
        writer.writerows(rows_vil)

    # Override manifest hashes for test files
    import hashlib
    from py_nusantara.manifest import Manifest
    for name, path in [("provinces.csv.gz", mock_prov), ("regencies.csv.gz", mock_reg), ("districts.csv.gz", mock_dist), ("villages_11.csv.gz", mock_vil)]:
        sha = hashlib.sha256()
        with open(path, "rb") as file_bin:
            while chunk := file_bin.read(8192):
                sha.update(chunk)
        Manifest.HASHES[name] = sha.hexdigest()

    config_dict = {
        "columns": {
            "provinces": {"boundary": {"name": "boundary", "enabled": True}},
            "regencies": {"boundary": {"name": "boundary", "enabled": True}},
            "districts": {"boundary": {"name": "boundary", "enabled": True}},
            "villages": {"boundary": {"name": "boundary", "enabled": True}},
        },
        "boundaries": {
            "local_path": str(tmp_path),
            "verify_checksum": True
        }
    }
    
    nus = Nusantara(config_dict)
    nus.clear_cache()
    
    # 5.5, 95.4 falls inside the polygons of all 4 mock entities
    res = nus.find_by_coordinate(5.5, 95.4, fallback_to_nearest=False)
    
    assert res["province"] is not None
    assert res["province"].name == "Aceh"
    assert res["regency"] is not None
    assert res["regency"].name == "Kabupaten Aceh Selatan"
    assert res["district"] is not None
    assert res["district"].name == "Bakongan"
    assert res["village"] is not None
    assert res["village"].name == "Keude Bakongan"


def test_nik_validation_and_parsing():
    import datetime
    
    # 1. Valid Male NIK (Bakongan, Aceh, born 4 Feb 2002)
    nik_male = "1101010402020001"
    assert validate_nik(nik_male) is True
    
    info = parse_nik(nik_male)
    assert isinstance(info, NIKInfo)
    assert info.nik == nik_male
    assert info.province_id == "11"
    assert info.regency_id == "1101"
    assert info.district_id == "110101"
    assert info.gender == "male"
    assert info.birth_date == datetime.date(2002, 2, 4)
    assert info.sequence == "0001"
    
    # Check regional resolution
    assert info.province is not None
    assert info.province.name == "Aceh"
    assert info.regency is not None
    assert info.regency.name == "Kabupaten Aceh Selatan"
    assert info.district is not None
    assert info.district.name == "Bakongan"
    
    # 2. Valid Female NIK (same birth date, female day = 4 + 40 = 44)
    nik_female = "1101014402020001"
    assert validate_nik(nik_female) is True
    
    info_female = parse_nik(nik_female)
    assert info_female.gender == "female"
    assert info_female.birth_date == datetime.date(2002, 2, 4)

    # 3. Invalid NIK: Format checks
    assert validate_nik("110101040202000") is False  # Too short
    assert validate_nik("11010104020200011") is False # Too long
    assert validate_nik("110101040202000A") is False  # Non-numeric
    
    with pytest.raises(NIKValidationError, match="exactly 16 characters"):
        parse_nik("110101040202000")
        
    with pytest.raises(NIKValidationError, match="only numeric digits"):
        parse_nik("110101040202000A")

    # 4. Invalid NIK: Sub-codes and ranges
    assert validate_nik("0001010402020001") is False  # Province '00'
    assert validate_nik("1100010402020001") is False  # Regency '00'
    assert validate_nik("1101000402020001") is False  # District '00'
    assert validate_nik("1101010402020000") is False  # Sequence '0000'
    
    with pytest.raises(NIKValidationError, match="Province code cannot be '00'"):
        parse_nik("0001010402020001")

    # 5. Invalid NIK: Birth Date validation
    assert validate_nik("1101013202020001") is False  # Day 32
    assert validate_nik("1101010413020001") is False  # Month 13
    assert validate_nik("1101013104020001") is False  # April 31st
    assert validate_nik("1101012902030001") is False  # Feb 29 on non-leap year (2003)
    
    # Valid leap year date
    assert validate_nik("1101012902040001") is True   # Feb 29 on leap year (2004)

    # 6. Century threshold heuristic
    # reference year = 2026
    # '26' -> 2026
    info_26 = parse_nik("1101010402260001", reference_year=2026)
    assert info_26.birth_date.year == 2026
    
    # '27' -> 1927 (since 2027 > 2026)
    info_27 = parse_nik("1101010402270001", reference_year=2026)
    assert info_27.birth_date.year == 1927

    # 7. Unregistered / Unknown regional codes (should parse details but return None for records)
    nik_unknown = "9999990402020001"
    assert validate_nik(nik_unknown) is True
    
    info_unknown = parse_nik(nik_unknown)
    assert info_unknown.province_id == "99"
    assert info_unknown.regency_id == "9999"
    assert info_unknown.district_id == "999999"
    assert info_unknown.gender == "male"
    assert info_unknown.birth_date == datetime.date(2002, 2, 4)
    
    # Since codes 999999 do not exist in the database:
    assert info_unknown.province is None
    assert info_unknown.regency is None
    assert info_unknown.district is None


def test_postal_code_validation_and_parsing():
    # 1. Valid validation
    assert validate_postal_code("23773") is True
    assert validate_postal_code("12345") is True
    
    # 2. Invalid validation
    assert validate_postal_code("1234") is False   # Too short
    assert validate_postal_code("123456") is False # Too long
    assert validate_postal_code("1234a") is False  # Non-numeric
    assert validate_postal_code("01234") is False  # Starts with 0
    assert validate_postal_code(None) is False     # Non-string
    
    # 3. Exception raising
    with pytest.raises(PostalCodeValidationError, match="Must be exactly 5 numeric digits"):
        parse_postal_code("1234")
        
    with pytest.raises(PostalCodeValidationError, match="cannot start with '0'"):
        parse_postal_code("01234")

    # 4. Valid lookup & resolution (using real postal code '23773' from Keude Bakongan)
    clear_cache()
    info = parse_postal_code("23773")
    assert isinstance(info, PostalCodeInfo)
    assert info.postal_code == "23773"
    assert len(info.villages) > 0
    
    # Verify Keude Bakongan is found
    names = [v.name for v in info.villages]
    assert "Keude Bakongan" in names
    
    # Verify parents resolved
    assert len(info.districts) > 0
    assert info.districts[0].name == "Bakongan"
    
    assert len(info.regencies) > 0
    assert info.regencies[0].name == "Kabupaten Aceh Selatan"
    
    assert len(info.provinces) > 0
    assert info.provinces[0].name == "Aceh"
    
    # Verify dictionary export
    d = info.to_dict()
    assert d["postal_code"] == "23773"
    assert len(d["villages"]) > 0
    assert d["villages"][0]["name"] == "Keude Bakongan"
    assert d["districts"][0]["name"] == "Bakongan"

    # 5. Non-existent but valid format
    info_none = parse_postal_code("99999")
    assert info_none.postal_code == "99999"
    assert len(info_none.villages) == 0
    assert len(info_none.districts) == 0
    assert len(info_none.regencies) == 0
    assert len(info_none.provinces) == 0


def test_region_enhancements():
    # 1. Relationship shortcuts
    # Keude Bakongan ID = '1101012001'
    village = find_village("1101012001")
    assert village is not None
    assert village.regency is not None
    assert village.regency.name == "Kabupaten Aceh Selatan"
    assert village.province is not None
    assert village.province.name == "Aceh"
    
    # District Bakongan ID = '110101'
    district = find_district("110101")
    assert district is not None
    assert district.province is not None
    assert district.province.name == "Aceh"
    
    # 2. City vs Regency classifications
    # Kota Banda Aceh ID = '1171' (or matches startswith "KOTA")
    banda_aceh = find_regency("1171")
    assert banda_aceh is not None
    assert banda_aceh.is_city is True
    assert banda_aceh.type == "Kota"
    
    # Kabupaten Aceh Selatan ID = '1101'
    aceh_selatan = find_regency("1101")
    assert aceh_selatan is not None
    assert aceh_selatan.is_city is False
    assert aceh_selatan.type == "Kabupaten"
    
    # 3. Regional code utilities
    assert clean_region_code("32.73.01.2001") == "3273012001"
    assert clean_region_code("  32.73  ") == "3273"
    
    assert format_region_code("32") == "32"
    assert format_region_code("3273") == "32.73"
    assert format_region_code("327301") == "32.73.01"
    assert format_region_code("3273012001") == "32.73.01.2001"
    
    with pytest.raises(TypeError):
        clean_region_code(1234)
    with pytest.raises(TypeError):
        format_region_code(1234)
    with pytest.raises(ValueError):
        format_region_code("123")
    with pytest.raises(ValueError):
        format_region_code("3273012001A")
        
    assert validate_region_code("32.73.01.2001") is True
    assert validate_region_code("12345") is False
    assert validate_region_code("32730a") is False
    assert validate_region_code(None) is False

    # 4. Scoped searches
    clear_cache()
    # "Bakongan" matches districts / villages in Aceh (Province '11', Regency '1101')
    
    # Scoped to province '11' -> should find it
    res_in_scope = search("Bakongan", scope={"province_id": "11"})
    assert len(res_in_scope["districts"]) > 0
    assert res_in_scope["districts"][0].id.startswith("11")
    
    # Scoped to province '32' (Jawa Barat) -> should NOT find it
    res_out_scope = search("Bakongan", scope={"province_id": "32"})
    assert len(res_out_scope["districts"]) == 0
    assert len(res_out_scope["villages"]) == 0
    
    # Scoped to regency '1101' -> should find it
    res_reg_scope = search("Bakongan", scope={"regency_id": "1101"})
    assert len(res_reg_scope["districts"]) > 0
    
    # Scoped to regency '1102' -> should NOT find it
    res_reg_out = search("Bakongan", scope={"regency_id": "1102"})
    assert len(res_reg_out["districts"]) == 0
    assert len(res_reg_out["villages"]) == 0


def test_spatial_and_gis_helpers():
    # 1. Distance Calculation (distance_to)
    # Regency Aceh Selatan (1101) & Kota Banda Aceh (1171)
    r1 = find_regency("1101")
    r2 = find_regency("1171")
    
    assert r1 is not None
    assert r2 is not None
    
    dist = r1.distance_to(r2)
    assert isinstance(dist, float)
    assert dist > 0.0
    
    # Distance to self should be 0.0
    assert r1.distance_to(r1) == 0.0
    
    # TypeError check
    with pytest.raises(TypeError):
        r1.distance_to("not a record")
        
    # None return when missing coordinates
    r1._data["latitude"] = None
    assert r1.distance_to(r2) is None
    
    # Restore latitude
    r1._data["latitude"] = "3.2"

    # 2. Radial Search (find_nearby)
    # Coordinates of Banda Aceh: lat=5.54, lon=95.32
    nearby_provs = find_nearby(5.54, 95.32, radius_km=100.0, level="provinces")
    assert len(nearby_provs) > 0
    assert nearby_provs[0].name == "Aceh"
    assert hasattr(nearby_provs[0], "distance_km")
    assert nearby_provs[0].distance_km < 100.0
    
    # Sorting check (nearest first)
    if len(nearby_provs) > 1:
        assert nearby_provs[0].distance_km <= nearby_provs[1].distance_km
        
    # Invalid level check
    with pytest.raises(ValueError, match="level must be one of"):
        find_nearby(5.54, 95.32, radius_km=100.0, level="invalid_level")

    # Pruned villages nearby search (Banda Aceh has villages starting with '11')
    nearby_villages = find_nearby(5.54, 95.32, radius_km=50.0, level="villages")
    assert len(nearby_villages) > 0
    for v in nearby_villages:
        assert v.id.startswith("11")  # Must belong to Aceh
        assert v.distance_km <= 50.0


def test_village_classification():
    # 1. Kelurahan test (digit 7 = 1)
    from py_nusantara import VillageRecord
    from py_nusantara.config import NusantaraConfig
    cfg = NusantaraConfig()
    
    # Kelurahan: 1201011001 (7th char is 1)
    kelurahan = VillageRecord({"id": "1201011001", "name": "Pasar Batu Gerigis"}, cfg)
    assert kelurahan.is_kelurahan is True
    assert kelurahan.is_desa is False
    assert kelurahan.type == "Kelurahan"
    
    # Desa: 1101012001 (7th char is 2)
    desa = VillageRecord({"id": "1101012001", "name": "Keude Bakongan"}, cfg)
    assert desa.is_kelurahan is False
    assert desa.is_desa is True
    assert desa.type == "Desa"


def test_localized_nomenclature():
    from py_nusantara import VillageRecord, DistrictRecord
    from py_nusantara.config import NusantaraConfig
    cfg = NusantaraConfig()

    # Village in Aceh (Province 11) -> Gampong
    v_aceh = VillageRecord({"id": "1101012001", "name": "Keude Bakongan"}, cfg)
    assert v_aceh.localized_type == "Gampong"

    # Village in West Sumatra (Province 13) -> Nagari
    v_sumbar = VillageRecord({"id": "1301012001", "name": "Musi"}, cfg)
    assert v_sumbar.localized_type == "Nagari"

    # Village in Papua (Province 91) -> Kampung
    v_papua = VillageRecord({"id": "9101012001", "name": "A"}, cfg)
    assert v_papua.localized_type == "Kampung"

    # Village in West Java (Province 32) -> Desa (standard)
    v_jabar = VillageRecord({"id": "3201012001", "name": "B"}, cfg)
    assert v_jabar.localized_type == "Desa"

    # District in Yogyakarta City (3471...) -> Kemantren
    d_jogja_city = DistrictRecord({"id": "347101", "name": "Danurejan"}, cfg)
    assert d_jogja_city.localized_type == "Kemantren"

    # District in Yogyakarta Regency Bantul (3402...) -> Kapanewon
    d_jogja_reg = DistrictRecord({"id": "340201", "name": "Srandakan"}, cfg)
    assert d_jogja_reg.localized_type == "Kapanewon"

    # District in Jakarta (3171...) -> Kecamatan (standard)
    d_jakarta = DistrictRecord({"id": "317101", "name": "Menteng"}, cfg)
    assert d_jakarta.localized_type == "Kecamatan"


def test_historical_split_mapping_and_resolution():
    from py_nusantara import resolve_legacy_id, parse_nik, find_regency, find_district, find_village
    
    # Test resolve_legacy_id direct mapping
    assert resolve_legacy_id("9101") == "9301"  # Merauke: old Papua -> Papua Selatan
    assert resolve_legacy_id("910101") == "930101"
    assert resolve_legacy_id("9101012001") == "9301012001"
    assert resolve_legacy_id("1101") == "1101"  # Non-split unchanged

    # Test transparent lookup fallback through facade
    # 9101 is Merauke (old Papua). In our active dataset, Merauke is 9301.
    merauke_regency = find_regency("9101")
    assert merauke_regency is not None
    assert merauke_regency.id == "9301"
    assert merauke_regency.name == "Kabupaten Merauke"

    # Test district lookup fallback
    merauke_district = find_district("910101")
    assert merauke_district is not None
    assert merauke_district.id == "930101"
    assert merauke_district.name == "Merauke"

    # Test village lookup fallback
    samkai_village = find_village("9101011002")
    assert samkai_village is not None
    assert samkai_village.id == "9301011002"
    assert samkai_village.name == "Samkai"
    assert samkai_village.is_kelurahan is True

    # Test legacy NIK resolution
    # Legacy NIK: starts with 910101 (Merauke District, Papua)
    legacy_nik = "9101010402020001"
    info = parse_nik(legacy_nik)
    assert info.province_id == "91"
    assert info.regency_id == "9101"
    assert info.district_id == "910101"
    
    # These should resolve to active records in Papua Selatan / Merauke
    assert info.province is not None
    assert info.province.id == "93"
    assert info.province.name == "Papua Selatan"
    
    assert info.regency is not None
    assert info.regency.id == "9301"
    assert info.regency.name == "Kabupaten Merauke"
    
    assert info.district is not None
    assert info.district.id == "930101"
    assert info.district.name == "Merauke"


def test_spatial_index_kd_tree():
    from py_nusantara.spatial import KDTree, latlon_to_3d
    from py_nusantara.records import ProvinceRecord
    from py_nusantara.config import NusantaraConfig
    import math

    cfg = NusantaraConfig()
    p1 = ProvinceRecord({"id": "11", "name": "Aceh", "latitude": "5.5", "longitude": "95.3"}, cfg)
    p2 = ProvinceRecord({"id": "12", "name": "North Sumatra", "latitude": "2.1", "longitude": "99.1"}, cfg)
    p3 = ProvinceRecord({"id": "13", "name": "West Sumatra", "latitude": "-0.9", "longitude": "100.3"}, cfg)

    tree = KDTree([p1, p2, p3])
    
    q_lat, q_lon = 5.4, 95.2
    q_3d = latlon_to_3d(q_lat, q_lon)
    
    r_3d = 2.0 * math.sin((50.0 / 6371.0) / 2.0)
    res_radius = tree.query_radius(q_3d, r_3d)
    assert len(res_radius) == 1
    assert res_radius[0][1].name == "Aceh"

    res_knn = tree.query_knn(q_3d, 2)
    assert len(res_knn) == 2
    assert res_knn[0][1].name == "Aceh"
    assert res_knn[1][1].name == "North Sumatra"


def test_find_knn_api():
    from py_nusantara import find_knn
    res = find_knn(5.54, 95.32, k=3, level="provinces")
    assert len(res) == 3
    assert res[0].name == "Aceh"
    assert hasattr(res[0], "distance_km")
    assert res[0].distance_km <= res[1].distance_km
    assert res[1].distance_km <= res[2].distance_km


def test_to_geojson():
    from py_nusantara.records import ProvinceRecord
    from py_nusantara.config import NusantaraConfig
    
    cfg = NusantaraConfig({
        "columns": {
            "provinces": {
                "boundary": {"name": "boundary", "enabled": True}
            }
        }
    })
    
    p_point = ProvinceRecord({
        "id": "11",
        "name": "Aceh",
        "capital": "Banda Aceh",
        "latitude": "5.5",
        "longitude": "95.3",
        "boundary": None
    }, cfg)
    
    geojson = p_point.to_geojson()
    assert geojson["type"] == "Feature"
    assert geojson["geometry"]["type"] == "Point"
    assert geojson["geometry"]["coordinates"] == [95.3, 5.5]
    assert geojson["properties"]["name"] == "Aceh"
    assert "boundary" not in geojson["properties"]

    p_json = ProvinceRecord({
        "id": "11",
        "name": "Aceh",
        "latitude": "5.5",
        "longitude": "95.3",
        "boundary": "[[[5.5, 95.3], [5.6, 95.4], [5.5, 95.4], [5.5, 95.3]]]"
    }, cfg)
    geojson_json = p_json.to_geojson()
    assert geojson_json["geometry"]["type"] == "Polygon"
    assert geojson_json["geometry"]["coordinates"] == [[[95.3, 5.5], [95.4, 5.6], [95.4, 5.5], [95.3, 5.5]]]

    p_wkt = ProvinceRecord({
        "id": "11",
        "name": "Aceh",
        "latitude": "5.5",
        "longitude": "95.3",
        "boundary": "POLYGON((95.3 5.5, 95.4 5.6, 95.4 5.5, 95.3 5.5))"
    }, cfg)
    geojson_wkt = p_wkt.to_geojson()
    assert geojson_wkt["geometry"]["type"] == "Polygon"
    assert geojson_wkt["geometry"]["coordinates"] == [[[95.3, 5.5], [95.4, 5.6], [95.4, 5.5], [95.3, 5.5]]]


def test_geoalchemy2_orm_integration():
    import sys
    from types import ModuleType
    from sqlalchemy import create_engine
    from sqlalchemy.orm import declarative_base, sessionmaker
    from py_nusantara import build_models, NusantaraConfig

    original_geoalchemy2 = sys.modules.get("geoalchemy2")
    
    import sqlalchemy.types as satypes
    mock_ga = ModuleType("geoalchemy2")
    class MockGeometry(satypes.UserDefinedType):
        def __init__(self, geometry_type="GEOMETRY", srid=4326):
            self.geometry_type = geometry_type
            self.srid = srid
    mock_ga.Geometry = MockGeometry
    sys.modules["geoalchemy2"] = mock_ga

    try:
        cfg = NusantaraConfig({
            "columns": {
                "provinces": {"boundary": {"name": "boundary", "enabled": True}}
            },
            "boundaries": {
                "use_geoalchemy2": True
            }
        })
        
        Base = declarative_base()
        models = build_models(Base, cfg)
        
        assert models["Province"].boundary is not None
        assert isinstance(models["Province"].boundary.type, MockGeometry)
        assert models["Province"].boundary.type.geometry_type == "GEOMETRY"
        assert models["Province"].boundary.type.srid == 4326

        prov = models["Province"](
            id="11",
            name="Aceh",
            latitude=5.5,
            longitude=95.3,
            boundary="POLYGON((95.3 5.5, 95.4 5.6, 95.4 5.5, 95.3 5.5))"
        )
        geojson = prov.to_geojson()
        assert geojson["type"] == "Feature"
        assert geojson["geometry"]["type"] == "Polygon"
        assert geojson["geometry"]["coordinates"] == [[[95.3, 5.5], [95.4, 5.6], [95.4, 5.5], [95.3, 5.5]]]
        assert geojson["properties"]["name"] == "Aceh"

    finally:
        if original_geoalchemy2:
            sys.modules["geoalchemy2"] = original_geoalchemy2
        elif "geoalchemy2" in sys.modules:
            del sys.modules["geoalchemy2"]


def test_fuzzy_search():
    from py_nusantara import search, clear_cache
    clear_cache()

    # Test typo correction
    res_fuzzy = search("Makasar", fuzzy=True, threshold=0.7, similarity_method="levenshtein")
    regencies = [r.name for r in res_fuzzy["regencies"]]
    # Should correct "Makasar" -> "Kota Makassar"
    assert any("Makassar" in name for name in regencies)

    # Test "Jogjakarta" -> "Yogyakarta"
    res_fuzzy2 = search("Jogjakarta", fuzzy=True, threshold=0.6)
    provs = [p.name for p in res_fuzzy2["provinces"]]
    assert any("Yogyakarta" in name for name in provs)

    # Test "Jogjakarta" -> "Yogyakarta" using trigram
    res_trigram = search("Jogjakarta", fuzzy=True, threshold=0.3, similarity_method="trigram")
    provs_tri = [p.name for p in res_trigram["provinces"]]
    assert any("Yogyakarta" in name for name in provs_tri)



def test_bbox_query(tmp_path):
    import gzip
    import csv
    from py_nusantara import Nusantara
    
    # Create mock cache files containing boundaries
    mock_prov = tmp_path / "provinces.csv.gz"
    headers = ["id", "name", "capital", "latitude", "longitude", "elevation", "timezone", "area", "population", "boundary"]
    rows = [["11", "Aceh", "Banda Aceh", "5.5", "95.3", "12.0", "WIB", "56789.0", "5000000", "[[[5.0, 95.0], [6.0, 95.0], [6.0, 96.0], [5.0, 96.0], [5.0, 95.0]]]"]]
    with gzip.open(mock_prov, "wt", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)

    import hashlib
    from py_nusantara.manifest import Manifest
    sha = hashlib.sha256()
    with open(mock_prov, "rb") as file_bin:
        while chunk := file_bin.read(8192):
            sha.update(chunk)
    Manifest.HASHES["provinces.csv.gz"] = sha.hexdigest()

    config_dict = {
        "columns": {
            "provinces": {"boundary": {"name": "boundary", "enabled": True}},
        },
        "boundaries": {
            "local_path": str(tmp_path),
            "verify_checksum": True
        }
    }
    
    nus = Nusantara(config_dict)
    nus.clear_cache()
    
    # Query bbox containing the centroid (5.5, 95.3)
    res_centroid = nus.find_in_bbox(5.4, 95.2, 5.6, 95.4, level="provinces")
    assert len(res_centroid) == 1
    assert res_centroid[0].name == "Aceh"

    # Query bbox outside centroid but intersecting the boundary polygon
    # Polygon is [5.0, 95.0] to [6.0, 96.0].
    # Bbox [5.1, 95.1] to [5.3, 95.2] does NOT contain the centroid (5.5, 95.3),
    # but overlaps the boundary polygon.
    res_boundary = nus.find_in_bbox(5.1, 95.1, 5.3, 95.2, level="provinces", use_boundary=True)
    assert len(res_boundary) == 1
    assert res_boundary[0].name == "Aceh"


def test_async_database_seeding(tmp_path):
    import asyncio
    import gzip
    import csv
    from py_nusantara import build_models, NusantaraConfig
    
    # Set up mock cache file for boundary
    mock_prov = tmp_path / "provinces.csv.gz"
    headers = ["id", "name", "capital", "latitude", "longitude", "elevation", "timezone", "area", "population", "boundary"]
    rows = [["11", "Aceh", "Banda Aceh", "5.5", "95.3", "12.0", "WIB", "56789.0", "5000000", "[[[5.5, 95.3], [5.6, 95.4], [5.5, 95.4], [5.5, 95.3]]]"]]
    with gzip.open(mock_prov, "wt", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)

    import hashlib
    from py_nusantara.manifest import Manifest
    sha = hashlib.sha256()
    with open(mock_prov, "rb") as file_bin:
        while chunk := file_bin.read(8192):
            sha.update(chunk)
    Manifest.HASHES["provinces.csv.gz"] = sha.hexdigest()

    async def run_async_test():
        from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
        from sqlalchemy.orm import declarative_base
        
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        
        cfg = NusantaraConfig({
            "columns": {
                "provinces": {"boundary": {"name": "boundary", "enabled": True}}
            },
            "boundaries": {
                "local_path": str(tmp_path),
                "type": "text",  # Use text type to simplify SQLite testing
            }
        })
        
        Base = declarative_base()
        models = build_models(Base, cfg)
        
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            
        from py_nusantara import NusantaraReader, NusantaraSeeder
        reader = NusantaraReader(cfg)
        
        async_session = AsyncSession(engine)
        
        seeder = NusantaraSeeder(async_session, cfg, reader)
        
        # Test core async seeding
        await seeder.seed_async()
        
        # Query database asynchronously to verify core seeding
        from sqlalchemy import select
        result = await async_session.execute(select(models["Province"]).filter_by(id="11"))
        db_prov = result.scalar_one_or_none()
        assert db_prov is not None
        assert db_prov.name == "Aceh"
        
        # Test async boundaries seeding
        await seeder.seed_boundaries_async(levels=["provinces"], force=True)
        
        result_b = await async_session.execute(select(models["Province"]).filter_by(id="11"))
        db_prov_b = result_b.scalar_one_or_none()
        assert db_prov_b.boundary is not None
        assert "5.5" in db_prov_b.boundary
        
        await async_session.close()
        await engine.dispose()

    try:
        import aiosqlite
        asyncio.run(run_async_test())
    except ImportError:
        # If aiosqlite is not available in test environment, we pass
        pass


