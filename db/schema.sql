-- ========================================================
-- Schema CSDL Dự án DuLich (PostgreSQL)
-- Đảm bảo Idempotent: chạy nhiều lần không lỗi
-- ========================================================

CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(255) NOT NULL,
    is_admin BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS user_preferences (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    preference_type VARCHAR(50) NOT NULL,
    preference_value VARCHAR(100) NOT NULL,
    CONSTRAINT uq_user_pref UNIQUE (user_id, preference_type, preference_value)
);

CREATE TABLE IF NOT EXISTS categories (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,
    icon VARCHAR(100) NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS destinations (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    province VARCHAR(100) NOT NULL,
    address VARCHAR(255) NOT NULL DEFAULT '',
    latitude DOUBLE PRECISION NOT NULL,
    longitude DOUBLE PRECISION NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    image_url VARCHAR(500) NOT NULL DEFAULT '',
    category_id INTEGER REFERENCES categories(id) ON DELETE SET NULL,
    price_range INTEGER NOT NULL CHECK (price_range BETWEEN 1 AND 4),
    noise_level INTEGER NOT NULL CHECK (noise_level BETWEEN 1 AND 5),
    duration_hours DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    is_outdoor BOOLEAN NOT NULL DEFAULT TRUE,
    opening_hours JSONB,
    tags JSONB NOT NULL DEFAULT '[]'::jsonb,
    avg_rating DOUBLE PRECISION,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS trips (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title VARCHAR(255) NOT NULL,
    destination_province VARCHAR(100) NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    total_days INTEGER NOT NULL,
    budget BIGINT NOT NULL,
    num_people INTEGER NOT NULL,
    travel_style VARCHAR(50) NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'draft',
    is_public BOOLEAN NOT NULL DEFAULT FALSE,
    share_token VARCHAR(100) UNIQUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS itinerary_items (
    id SERIAL PRIMARY KEY,
    trip_id INTEGER NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
    destination_id INTEGER NOT NULL REFERENCES destinations(id) ON DELETE CASCADE,
    day_number INTEGER NOT NULL,
    time_slot VARCHAR(20) NOT NULL,
    order_in_slot INTEGER NOT NULL,
    estimated_cost BIGINT NOT NULL DEFAULT 0,
    notes TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS ratings (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    destination_id INTEGER NOT NULL REFERENCES destinations(id) ON DELETE CASCADE,
    trip_id INTEGER REFERENCES trips(id) ON DELETE SET NULL,
    score INTEGER NOT NULL CHECK (score BETWEEN 1 AND 5),
    review_text TEXT NOT NULL DEFAULT '',
    is_approved BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS weather_cache (
    id SERIAL PRIMARY KEY,
    province VARCHAR(100) NOT NULL UNIQUE,
    weather_data JSONB NOT NULL,
    cached_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Chỉ mục hỗ trợ truy vấn nhanh
CREATE INDEX IF NOT EXISTS idx_destinations_province ON destinations(province);
CREATE INDEX IF NOT EXISTS idx_trips_user_id ON trips(user_id);
CREATE INDEX IF NOT EXISTS idx_itinerary_items_trip ON itinerary_items(trip_id);
CREATE INDEX IF NOT EXISTS idx_ratings_destination ON ratings(destination_id);
CREATE INDEX IF NOT EXISTS idx_ratings_approved ON ratings(is_approved);
