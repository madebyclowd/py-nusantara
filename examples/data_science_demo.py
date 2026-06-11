import py_nusantara as nus

def main():
    print("--- 1. Direct Data Access (No Database) ---")
    
    # 1. Fetch all provinces
    provinces = nus.provinces()
    print(f"Total Provinces: {len(provinces)}")
    
    # 2. Get a specific province by ID (Aceh: '11')
    province = nus.find_province("11")
    print(f"Province Found: {province}")
    print(f"Capital: {province.capital}")
    print(f"Latitude: {province.latitude}, Longitude: {province.longitude}")
    print(f"Population: {province.population:,}")
    print(f"Area: {province.area:,} km²")
    
    # 3. Traversal (Province -> Regencies -> Districts -> Villages)
    print("\n--- 2. Relationship Traversals ---")
    regencies = province.regencies
    print(f"Regencies in {province.name}: {len(regencies)}")
    first_regency = regencies[0]
    print(f"First Regency: {first_regency.name} (belongs to Province: {first_regency.province.name})")
    
    districts = first_regency.districts
    print(f"Districts in {first_regency.name}: {len(districts)}")
    first_district = districts[0]
    
    villages = first_district.villages
    print(f"Villages in {first_district.name}: {len(villages)}")
    if villages:
        first_village = villages[0]
        print(f"First Village: {first_village.name} (Postal Code: {first_village.postal_code}, District: {first_village.district.name})")
    
    # 4. Search functionality
    print("\n--- 3. Search ---")
    query = "Bakongan"
    print(f"Searching for '{query}'...")
    results = nus.search(query)
    for level, records in results.items():
        if records:
            print(f"Found in {level}: {[r.name for r in records]}")

    # 5. Geographic Boundaries Download and Loading
    print("\n--- 4. Geographic Boundaries (GIS) ---")
    
    # Enable boundary column in config dynamically
    nus.init({
        "columns": {
            "provinces": {
                "boundary": {"name": "boundary", "enabled": True}
            }
        }
    })
    
    print("Downloading boundary file for provinces (on-demand)...")
    def on_download_progress(event_name, msg):
        print(f"  [{event_name.upper()}] {msg}")
        
    # Download provinces boundary (verified with checksum!)
    nus.download_boundaries(levels="provinces", progress_callback=on_download_progress)
    
    # Re-fetch province to access boundary coordinate JSON
    aceh_with_boundary = nus.find_province("11")
    print(f"Province boundary string (truncated): {aceh_with_boundary.boundary[:100]}...")
    
    # Test JSON-to-WKT formatting helper
    wkt = nus.json_to_wkt(aceh_with_boundary.boundary)
    print(f"WKT spatial format (truncated): {wkt[:100]}...")

    # 6. Convert to Pandas DataFrame for data analysis
    print("\n--- 5. Conversion to Pandas DataFrame ---")
    try:
        df_prov = nus.provinces_df()
        print("Provinces DataFrame (with boundary columns):")
        print(df_prov[["id", "name", "capital", "boundary"]].head(5))
        
        # Query regencies as DataFrame
        df_reg = nus.regencies_df(province.id)
        print(f"\nRegencies in Province {province.name} DataFrame:")
        print(df_reg.head(5))
    except ImportError:
        print("Pandas is not installed in the environment; skipping DataFrame demo.")


if __name__ == "__main__":
    main()
