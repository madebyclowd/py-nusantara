import asyncio
from py_nusantara import (
    Nusantara,
    init_spatial_indexes_async,
    search,
    find_by_coordinate,
    find_adjacent,
    to_geodataframe
)

# 1. Configuration for high-performance Zero-DB mode in microservices (e.g. Gunicorn/Uvicorn workers)
CONFIG = {
    # Enable Shared Memory so the heavy KD-Tree and parsed datasets are shared 
    # across multiple worker processes without memory duplication.
    "shared_memory": {
        "enabled": True,
        "prefix": "nusantara_zero_db_shm"
    },
    "cache": {
        "enabled": True,
        "ttl": 86400,
        "prefix": "nusantara_api_cache",
        "redis_url": None,                        # Set to your Redis URL to enable Redis cache (e.g. "redis://localhost:6379/0")
        "redis_pickle": False                     # Enable pickling cache objects (e.g., KDTree, records)
    }
}


async def main():
    print("--- 1. Initializing Nusantara Facade (Zero-DB Mode) ---")
    # Initialize the global instance with our configuration
    nus = Nusantara(CONFIG)

    # Pre-build KD-Tree spatial indexes asynchronously to prevent Uvicorn/Gunicorn 
    # readiness probe timeouts during ASGI startup.
    print("Pre-building spatial indexes asynchronously in background thread pool...")
    await init_spatial_indexes_async(levels=["provinces", "regencies"])
    print("Spatial indexes initialized successfully.")

    print("\n--- 2. Autocomplete Search with Pagination ---")
    # Query matching regions, using offset and cursor for paginating search results
    search_res = search("Aceh", limit=5)
    print(f"Standard Search match count: {len(search_res['provinces'])} provinces")

    if search_res["provinces"]:
        first_prov = search_res["provinces"][0]
        print(f"First province matching search: {first_prov.name} (ID: {first_prov.id})")
        
        # Paginate using cursor (returns elements lexicographically greater than the cursor ID)
        cursor_res = search("Aceh", limit=5, cursor=first_prov.id)
        print(f"Paginated Search results after cursor '{first_prov.id}':")
        for p in cursor_res["provinces"]:
            print(f" - {p.name} (ID: {p.id})")

    print("\n--- 3. Reverse Geocoding via KD-Tree Proximity ---")
    # Resolve the administrative hierarchy containing or closest to coordinates
    lat, lon = 5.54, 95.32 # Banda Aceh coordinates
    address = find_by_coordinate(lat, lon, fallback_to_nearest=True)
    print(f"Resolved location for ({lat}, {lon}):")
    print(f" - Province: {address['province'].name if address['province'] else 'None'}")
    print(f" - Regency : {address['regency'].name if address['regency'] else 'None'}")
    print(f" - District: {address['district'].name if address['district'] else 'None'}")
    print(f" - Village : {address['village'].name if address['village'] else 'None'}")

    print("\n--- 4. Topological Adjacency Query ---")
    # Resolve neighboring administrative divisions sharing a polygon boundary (touches check)
    aceh_province = find_by_coordinate(lat, lon)["province"]
    if aceh_province:
        try:
            print(f"Finding provinces adjacent to {aceh_province.name}...")
            neighbors = find_adjacent(aceh_province, level="provinces")
            for neighbor in neighbors:
                print(f" - Neighbor: {neighbor.name} (ID: {neighbor.id})")
        except ImportError:
            print("Shapely is required to perform topological touches queries.")

    print("\n--- 5. GeoPandas Spatial Data Science Integration ---")
    try:
        # Convert records to a spatial GeoDataFrame with shapely geometries
        provs = nus.provinces()[:3]
        gdf = to_geodataframe(provs)
        print("Successfully exported regional records to GeoDataFrame:")
        print(gdf[["id", "name", "geometry"]])
    except ImportError:
        print("GeoPandas and Shapely are required to export to GeoDataFrame.")


if __name__ == "__main__":
    asyncio.run(main())
