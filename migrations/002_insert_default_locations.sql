--
-- Migration: Insert default locations
-- Description: Inserts the 10 required geographic locations from ASSIGNMENT.md
--

INSERT INTO locations (lat, lon, name) VALUES
    (25.8600, -97.4200, 'Location 1 - Brownsville Area'),
    (25.9000, -97.5200, 'Location 2 - West Brownsville'),
    (25.9000, -97.4800, 'Location 3 - Central Brownsville'),
    (25.9000, -97.4400, 'Location 4 - East Brownsville'),
    (25.9000, -97.4000, 'Location 5 - Far East Brownsville'),
    (25.9200, -97.3800, 'Location 6 - Northeast Brownsville'),
    (25.9400, -97.5400, 'Location 7 - West Olmito'),
    (25.9400, -97.5200, 'Location 8 - Olmito Area'),
    (25.9400, -97.4800, 'Location 9 - North Brownsville'),
    (25.9400, -97.4400, 'Location 10 - North-Central Brownsville')
ON CONFLICT (lat, lon) DO NOTHING;

-- Verify insert
DO $$
BEGIN
    IF (SELECT COUNT(*) FROM locations) != 10 THEN
        RAISE EXCEPTION 'Expected 10 locations, found %', (SELECT COUNT(*) FROM locations);
    END IF;
END $$;
