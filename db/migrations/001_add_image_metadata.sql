-- Migration 001: Thêm trường quản lý ảnh Cloudinary và ghi công bản quyền tác giả
-- Idempotent: chạy an toàn nhiều lần mà không gây lỗi

ALTER TABLE destinations ADD COLUMN IF NOT EXISTS image_public_id VARCHAR(255);
ALTER TABLE destinations ADD COLUMN IF NOT EXISTS image_source VARCHAR(50) NOT NULL DEFAULT 'placeholder';
ALTER TABLE destinations ADD COLUMN IF NOT EXISTS image_author VARCHAR(255);
ALTER TABLE destinations ADD COLUMN IF NOT EXISTS image_license VARCHAR(50);
ALTER TABLE destinations ADD COLUMN IF NOT EXISTS image_source_url TEXT;
