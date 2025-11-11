-- DDL Wizard Advanced Test Data - Source Schema
-- Complex database with 30+ differences for comprehensive testing
-- Created: September 4, 2025

-- COMMENTED BY VIDEX
-- We prefer not to hardcode the database name; specify it via the MySQL/MariaDB import command instead
-- DROP DATABASE IF EXISTS ddw_test_src;
-- CREATE DATABASE IF NOT EXISTS ddw_test_src;
-- USE ddw_test_src;

-- Drop existing objects if they exist
DROP TABLE IF EXISTS order_items;
DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS product_reviews;
DROP TABLE IF EXISTS products;
DROP TABLE IF EXISTS user_profiles;
DROP TABLE IF EXISTS users;
DROP TABLE IF EXISTS categories;
DROP TABLE IF EXISTS audit_log;
DROP TABLE IF EXISTS system_config;
DROP TABLE IF EXISTS payment_methods;
DROP TABLE IF EXISTS shipping_addresses;
DROP TABLE IF EXISTS inventory_tracking;

DROP VIEW IF EXISTS customer_summary;
DROP VIEW IF EXISTS product_analytics;
DROP VIEW IF EXISTS order_statistics;
DROP VIEW IF EXISTS revenue_report;

DROP PROCEDURE IF EXISTS process_order;
DROP PROCEDURE IF EXISTS update_inventory;
DROP PROCEDURE IF EXISTS calculate_shipping;
DROP PROCEDURE IF EXISTS generate_report;

DROP FUNCTION IF EXISTS calculate_discount;
DROP FUNCTION IF EXISTS format_currency;
DROP FUNCTION IF EXISTS validate_email;
DROP FUNCTION IF EXISTS get_tax_rate;

DROP TRIGGER IF EXISTS users_audit_trigger;
DROP TRIGGER IF EXISTS inventory_update_trigger;
DROP TRIGGER IF EXISTS order_status_trigger;

DROP EVENT IF EXISTS cleanup_old_logs;
DROP EVENT IF EXISTS update_statistics;

DROP SEQUENCE IF EXISTS order_number_seq;
DROP SEQUENCE IF EXISTS invoice_number_seq;

-- =============================================================================
-- TABLES (12 tables with various configurations)
-- =============================================================================

-- Categories table with basic structure
CREATE TABLE categories (
    category_id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    description TEXT,
    parent_id INT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_parent_id (parent_id),
    INDEX idx_active (is_active),
    FOREIGN KEY (parent_id) REFERENCES categories(category_id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Product categories hierarchy';

-- Users table with comprehensive user management
CREATE TABLE users (
    user_id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) NOT NULL UNIQUE,
    email VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    first_name VARCHAR(100),
    last_name VARCHAR(100),
    phone VARCHAR(20),
    date_of_birth DATE,
    gender ENUM('Male', 'Female', 'Other') DEFAULT 'Other',
    status ENUM('Active', 'Inactive', 'Suspended', 'Pending') DEFAULT 'Pending',
    email_verified BOOLEAN DEFAULT FALSE,
    last_login TIMESTAMP NULL,
    failed_login_attempts INT DEFAULT 0,
    account_locked_until TIMESTAMP NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_username (username),
    INDEX idx_email (email),
    INDEX idx_status (status),
    INDEX idx_last_login (last_login),
    UNIQUE KEY uk_email_username (email, username)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='User account management';

-- User profiles with extended information
CREATE TABLE user_profiles (
    profile_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    avatar_url VARCHAR(500),
    bio TEXT,
    website VARCHAR(255),
    timezone VARCHAR(50) DEFAULT 'UTC',
    language VARCHAR(10) DEFAULT 'en',
    currency VARCHAR(3) DEFAULT 'USD',
    notification_preferences JSON,
    privacy_settings JSON,
    subscription_type ENUM('Free', 'Premium', 'Enterprise') DEFAULT 'Free',
    subscription_expires DATETIME NULL,
    total_purchases DECIMAL(12,2) DEFAULT 0.00,
    loyalty_points INT DEFAULT 0,
    referral_code VARCHAR(20) UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    INDEX idx_user_id (user_id),
    INDEX idx_subscription (subscription_type),
    INDEX idx_referral_code (referral_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Extended user profile information';

-- Products table with detailed product information
CREATE TABLE products (
    product_id INT AUTO_INCREMENT PRIMARY KEY,
    sku VARCHAR(50) NOT NULL UNIQUE,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    short_description VARCHAR(500),
    category_id INT,
    brand VARCHAR(100),
    model VARCHAR(100),
    weight DECIMAL(8,3),
    dimensions JSON,
    price DECIMAL(10,2) NOT NULL,
    cost DECIMAL(10,2),
    tax_class VARCHAR(50) DEFAULT 'standard',
    status ENUM('Draft', 'Active', 'Inactive', 'Discontinued') DEFAULT 'Draft',
    is_digital BOOLEAN DEFAULT FALSE,
    requires_shipping BOOLEAN DEFAULT TRUE,
    stock_quantity INT DEFAULT 0,
    low_stock_threshold INT DEFAULT 10,
    manage_stock BOOLEAN DEFAULT TRUE,
    allow_backorders BOOLEAN DEFAULT FALSE,
    featured BOOLEAN DEFAULT FALSE,
    downloadable_files JSON,
    meta_title VARCHAR(255),
    meta_description TEXT,
    meta_keywords VARCHAR(500),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (category_id) REFERENCES categories(category_id) ON DELETE SET NULL,
    INDEX idx_sku (sku),
    INDEX idx_category (category_id),
    INDEX idx_status (status),
    INDEX idx_featured (featured),
    -- FULLTEXT KEY ft_search (name, description, short_description), -- COMMENTED BY VIDEX
    INDEX idx_brand_model (brand, model)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Product catalog with detailed information';

-- Product reviews with rating system
CREATE TABLE product_reviews (
    review_id INT AUTO_INCREMENT PRIMARY KEY,
    product_id INT NOT NULL,
    user_id INT NOT NULL,
    rating TINYINT NOT NULL CHECK (rating BETWEEN 1 AND 5),
    title VARCHAR(255),
    review_text TEXT,
    is_verified_purchase BOOLEAN DEFAULT FALSE,
    helpful_votes INT DEFAULT 0,
    total_votes INT DEFAULT 0,
    status ENUM('Pending', 'Approved', 'Rejected', 'Spam') DEFAULT 'Pending',
    admin_notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (product_id) REFERENCES products(product_id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    INDEX idx_product_id (product_id),
    INDEX idx_user_id (user_id),
    INDEX idx_rating (rating),
    INDEX idx_status (status),
    INDEX idx_created_at (created_at),
    UNIQUE KEY uk_user_product (user_id, product_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Product reviews and ratings';

-- Orders table with comprehensive order management
CREATE TABLE orders (
    order_id INT AUTO_INCREMENT PRIMARY KEY,
    order_number VARCHAR(50) NOT NULL UNIQUE,
    user_id INT NOT NULL,
    status ENUM('Pending', 'Processing', 'Shipped', 'Delivered', 'Cancelled', 'Refunded') DEFAULT 'Pending',
    payment_status ENUM('Pending', 'Paid', 'Failed', 'Refunded', 'Partially_Refunded') DEFAULT 'Pending',
    currency VARCHAR(3) DEFAULT 'USD',
    subtotal DECIMAL(12,2) NOT NULL,
    tax_amount DECIMAL(12,2) DEFAULT 0.00,
    shipping_amount DECIMAL(12,2) DEFAULT 0.00,
    discount_amount DECIMAL(12,2) DEFAULT 0.00,
    total_amount DECIMAL(12,2) NOT NULL,
    payment_method VARCHAR(50),
    payment_reference VARCHAR(255),
    billing_address JSON,
    shipping_address JSON,
    shipping_method VARCHAR(100),
    tracking_number VARCHAR(100),
    notes TEXT,
    internal_notes TEXT,
    coupon_code VARCHAR(50),
    referral_source VARCHAR(100),
    ip_address VARCHAR(45),
    user_agent TEXT,
    shipped_at TIMESTAMP NULL,
    delivered_at TIMESTAMP NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE RESTRICT,
    INDEX idx_order_number (order_number),
    INDEX idx_user_id (user_id),
    INDEX idx_status (status),
    INDEX idx_payment_status (payment_status),
    INDEX idx_created_at (created_at),
    INDEX idx_total_amount (total_amount)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Customer orders with detailed tracking';

-- Order items with product details
CREATE TABLE order_items (
    item_id INT AUTO_INCREMENT PRIMARY KEY,
    order_id INT NOT NULL,
    product_id INT NOT NULL,
    product_sku VARCHAR(50) NOT NULL,
    product_name VARCHAR(255) NOT NULL,
    quantity INT NOT NULL,
    unit_price DECIMAL(10,2) NOT NULL,
    total_price DECIMAL(12,2) NOT NULL,
    product_options JSON,
    tax_amount DECIMAL(10,2) DEFAULT 0.00,
    discount_amount DECIMAL(10,2) DEFAULT 0.00,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (order_id) REFERENCES orders(order_id) ON DELETE CASCADE,
    FOREIGN KEY (product_id) REFERENCES products(product_id) ON DELETE RESTRICT,
    INDEX idx_order_id (order_id),
    INDEX idx_product_id (product_id),
    INDEX idx_product_sku (product_sku)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Individual items within orders';

-- System configuration table
CREATE TABLE system_config (
    config_id INT AUTO_INCREMENT PRIMARY KEY,
    config_key VARCHAR(100) NOT NULL UNIQUE,
    config_value TEXT,
    config_type ENUM('string', 'number', 'boolean', 'json') DEFAULT 'string',
    description TEXT,
    is_public BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_config_key (config_key),
    INDEX idx_is_public (is_public)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='System configuration settings';

-- Audit log for security tracking
CREATE TABLE audit_log (
    log_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id INT,
    action VARCHAR(100) NOT NULL,
    table_name VARCHAR(100),
    record_id VARCHAR(100),
    old_values JSON,
    new_values JSON,
    ip_address VARCHAR(45),
    user_agent TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_user_id (user_id),
    INDEX idx_action (action),
    INDEX idx_table_name (table_name),
    INDEX idx_created_at (created_at),
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='System audit trail';

-- Payment methods table
CREATE TABLE payment_methods (
    payment_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    method_type ENUM('Credit_Card', 'Debit_Card', 'PayPal', 'Bank_Transfer', 'Crypto') NOT NULL,
    provider VARCHAR(50),
    last_four_digits VARCHAR(4),
    expiry_month TINYINT,
    expiry_year SMALLINT,
    cardholder_name VARCHAR(255),
    is_default BOOLEAN DEFAULT FALSE,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    INDEX idx_user_id (user_id),
    INDEX idx_method_type (method_type),
    INDEX idx_is_default (is_default)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='User payment methods';

-- Shipping addresses
CREATE TABLE shipping_addresses (
    address_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    address_type ENUM('Home', 'Work', 'Other') DEFAULT 'Home',
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    company VARCHAR(255),
    address_line1 VARCHAR(255) NOT NULL,
    address_line2 VARCHAR(255),
    city VARCHAR(100) NOT NULL,
    state_province VARCHAR(100),
    postal_code VARCHAR(20),
    country VARCHAR(2) NOT NULL,
    phone VARCHAR(20),
    is_default BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    INDEX idx_user_id (user_id),
    INDEX idx_country (country),
    INDEX idx_is_default (is_default)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='User shipping addresses';

-- =============================================================================
-- SEQUENCES (2 sequences for order numbering)
-- =============================================================================

CREATE SEQUENCE order_number_seq 
    START WITH 100000 
    INCREMENT BY 1 
    MINVALUE 100000 
    MAXVALUE 999999999 
    CACHE 100 
    CYCLE;

CREATE SEQUENCE invoice_number_seq 
    START WITH 2025001 
    INCREMENT BY 1 
    MINVALUE 2025001 
    MAXVALUE 2099999999 
    CACHE 50 
    NOCYCLE;

-- =============================================================================
-- VIEWS (4 complex views for analytics)
-- =============================================================================

-- Customer summary view
CREATE VIEW customer_summary AS
SELECT 
    u.user_id,
    u.username,
    u.email,
    u.first_name,
    u.last_name,
    u.status AS account_status,
    up.subscription_type,
    up.total_purchases,
    up.loyalty_points,
    COUNT(DISTINCT o.order_id) AS total_orders,
    COALESCE(SUM(o.total_amount), 0) AS lifetime_value,
    AVG(o.total_amount) AS average_order_value,
    MAX(o.created_at) AS last_order_date,
    COUNT(DISTINCT pr.review_id) AS total_reviews,
    AVG(pr.rating) AS average_rating_given,
    u.created_at AS customer_since
FROM users u
LEFT JOIN user_profiles up ON u.user_id = up.user_id
LEFT JOIN orders o ON u.user_id = o.user_id AND o.status NOT IN ('Cancelled', 'Refunded')
LEFT JOIN product_reviews pr ON u.user_id = pr.user_id AND pr.status = 'Approved'
GROUP BY u.user_id, u.username, u.email, u.first_name, u.last_name, 
         u.status, up.subscription_type, up.total_purchases, up.loyalty_points, u.created_at;

-- Product analytics view
CREATE VIEW product_analytics AS
SELECT 
    p.product_id,
    p.sku,
    p.name,
    p.brand,
    c.name AS category_name,
    p.price,
    p.cost,
    p.stock_quantity,
    p.status,
    p.featured,
    COUNT(DISTINCT oi.order_id) AS total_orders,
    COALESCE(SUM(oi.quantity), 0) AS total_quantity_sold,
    COALESCE(SUM(oi.total_price), 0) AS total_revenue,
    COUNT(DISTINCT pr.review_id) AS total_reviews,
    AVG(pr.rating) AS average_rating,
    COALESCE(p.price * SUM(oi.quantity) - p.cost * SUM(oi.quantity), 0) AS estimated_profit,
    MAX(oi.created_at) AS last_sold_date
FROM products p
LEFT JOIN categories c ON p.category_id = c.category_id
LEFT JOIN order_items oi ON p.product_id = oi.product_id
LEFT JOIN orders o ON oi.order_id = o.order_id AND o.status NOT IN ('Cancelled', 'Refunded')
LEFT JOIN product_reviews pr ON p.product_id = pr.product_id AND pr.status = 'Approved'
GROUP BY p.product_id, p.sku, p.name, p.brand, c.name, p.price, p.cost, 
         p.stock_quantity, p.status, p.featured;

-- Order statistics view
CREATE VIEW order_statistics AS
SELECT 
    DATE(o.created_at) AS order_date,
    COUNT(DISTINCT o.order_id) AS total_orders,
    COUNT(DISTINCT o.user_id) AS unique_customers,
    SUM(o.total_amount) AS daily_revenue,
    AVG(o.total_amount) AS average_order_value,
    SUM(oi.quantity) AS total_items_sold,
    COUNT(CASE WHEN o.status = 'Delivered' THEN 1 END) AS delivered_orders,
    COUNT(CASE WHEN o.status = 'Cancelled' THEN 1 END) AS cancelled_orders,
    ROUND(COUNT(CASE WHEN o.status = 'Delivered' THEN 1 END) * 100.0 / COUNT(*), 2) AS delivery_rate
FROM orders o
LEFT JOIN order_items oi ON o.order_id = oi.order_id
WHERE o.created_at >= DATE_SUB(CURDATE(), INTERVAL 90 DAY)
GROUP BY DATE(o.created_at)
ORDER BY order_date DESC;

-- Revenue report view
CREATE VIEW revenue_report AS
SELECT 
    YEAR(o.created_at) AS revenue_year,
    MONTH(o.created_at) AS revenue_month,
    MONTHNAME(o.created_at) AS month_name,
    COUNT(DISTINCT o.order_id) AS total_orders,
    SUM(o.subtotal) AS gross_revenue,
    SUM(o.tax_amount) AS total_tax,
    SUM(o.shipping_amount) AS total_shipping,
    SUM(o.discount_amount) AS total_discounts,
    SUM(o.total_amount) AS net_revenue,
    AVG(o.total_amount) AS average_order_value,
    COUNT(DISTINCT o.user_id) AS unique_customers
FROM orders o
WHERE o.status NOT IN ('Cancelled', 'Refunded')
GROUP BY YEAR(o.created_at), MONTH(o.created_at), MONTHNAME(o.created_at)
ORDER BY revenue_year DESC, revenue_month DESC;

-- =============================================================================
-- STORED PROCEDURES (4 procedures for business logic)
-- =============================================================================

DELIMITER $$

-- Procedure to process a new order
CREATE PROCEDURE process_order(
    IN p_user_id INT,
    IN p_order_data JSON,
    OUT p_order_id INT,
    OUT p_result_message VARCHAR(255)
)
BEGIN
    DECLARE v_order_number VARCHAR(50);
    DECLARE v_total_amount DECIMAL(12,2) DEFAULT 0.00;
    DECLARE v_error_count INT DEFAULT 0;
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        SET p_result_message = 'Error processing order: Database error occurred';
        SET p_order_id = 0;
    END;

    START TRANSACTION;
    
    -- Generate order number
    SET v_order_number = CONCAT('ORD-', NEXTVAL(order_number_seq));
    
    -- Validate user exists and is active
    SELECT COUNT(*) INTO v_error_count 
    FROM users 
    WHERE user_id = p_user_id AND status = 'Active';
    
    IF v_error_count = 0 THEN
        SET p_result_message = 'Error: User not found or inactive';
        SET p_order_id = 0;
        ROLLBACK;
    ELSE
        -- Extract total amount from JSON
        SET v_total_amount = JSON_UNQUOTE(JSON_EXTRACT(p_order_data, '$.total_amount'));
        
        -- Create order
        INSERT INTO orders (
            order_number, user_id, status, payment_status, 
            currency, subtotal, tax_amount, shipping_amount, 
            total_amount, billing_address, shipping_address
        ) VALUES (
            v_order_number, p_user_id, 'Pending', 'Pending',
            'USD', v_total_amount, 0.00, 0.00,
            v_total_amount, 
            JSON_EXTRACT(p_order_data, '$.billing_address'),
            JSON_EXTRACT(p_order_data, '$.shipping_address')
        );
        
        SET p_order_id = LAST_INSERT_ID();
        SET p_result_message = CONCAT('Order created successfully: ', v_order_number);
        
        COMMIT;
    END IF;
END$$

-- Procedure to update inventory levels
CREATE PROCEDURE update_inventory(
    IN p_product_id INT,
    IN p_quantity_change INT,
    IN p_operation VARCHAR(20),
    OUT p_new_stock INT,
    OUT p_result_message VARCHAR(255)
)
update_inventory: BEGIN
    DECLARE v_current_stock INT DEFAULT 0;
    DECLARE v_new_stock INT DEFAULT 0;
    DECLARE v_low_threshold INT DEFAULT 0;
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        SET p_result_message = 'Error updating inventory: Database error occurred';
        SET p_new_stock = -1;
    END;

    START TRANSACTION;
    
    -- Get current stock level
    SELECT stock_quantity, low_stock_threshold 
    INTO v_current_stock, v_low_threshold
    FROM products 
    WHERE product_id = p_product_id;
    
    -- Calculate new stock based on operation
    IF p_operation = 'ADD' THEN
        SET v_new_stock = v_current_stock + p_quantity_change;
    ELSEIF p_operation = 'SUBTRACT' THEN
        SET v_new_stock = v_current_stock - p_quantity_change;
        IF v_new_stock < 0 THEN
            SET p_result_message = 'Error: Insufficient stock available';
            SET p_new_stock = v_current_stock;
            ROLLBACK;
            LEAVE update_inventory;
        END IF;
    ELSE
        SET v_new_stock = p_quantity_change;
    END IF;
    
    -- Update the stock
    UPDATE products 
    SET stock_quantity = v_new_stock,
        updated_at = CURRENT_TIMESTAMP
    WHERE product_id = p_product_id;
    
    SET p_new_stock = v_new_stock;
    
    -- Check if low stock warning needed
    IF v_new_stock <= v_low_threshold THEN
        SET p_result_message = CONCAT('Inventory updated. WARNING: Stock level (', v_new_stock, ') is at or below threshold (', v_low_threshold, ')');
    ELSE
        SET p_result_message = CONCAT('Inventory updated successfully. New stock level: ', v_new_stock);
    END IF;
    
    COMMIT;
END$$

-- Procedure to calculate shipping costs
CREATE PROCEDURE calculate_shipping(
    IN p_order_id INT,
    IN p_shipping_method VARCHAR(100),
    OUT p_shipping_cost DECIMAL(10,2),
    OUT p_result_message VARCHAR(255)
)
BEGIN
    DECLARE v_total_weight DECIMAL(10,3) DEFAULT 0.00;
    DECLARE v_item_count INT DEFAULT 0;
    DECLARE v_order_total DECIMAL(12,2) DEFAULT 0.00;
    
    -- Calculate total weight and item count
    SELECT 
        COALESCE(SUM(p.weight * oi.quantity), 0),
        SUM(oi.quantity),
        o.total_amount
    INTO v_total_weight, v_item_count, v_order_total
    FROM orders o
    JOIN order_items oi ON o.order_id = oi.order_id
    JOIN products p ON oi.product_id = p.product_id
    WHERE o.order_id = p_order_id;
    
    -- Calculate shipping based on method
    CASE p_shipping_method
        WHEN 'Standard' THEN
            IF v_order_total >= 50.00 THEN
                SET p_shipping_cost = 0.00;
            ELSE
                SET p_shipping_cost = 5.99;
            END IF;
        WHEN 'Express' THEN
            SET p_shipping_cost = 12.99 + (v_total_weight * 0.50);
        WHEN 'Overnight' THEN
            SET p_shipping_cost = 24.99 + (v_total_weight * 1.00);
        WHEN 'International' THEN
            SET p_shipping_cost = 19.99 + (v_total_weight * 2.00);
        ELSE
            SET p_shipping_cost = 5.99;
    END CASE;
    
    -- Update order with shipping cost
    UPDATE orders 
    SET shipping_amount = p_shipping_cost,
        shipping_method = p_shipping_method,
        total_amount = subtotal + tax_amount + p_shipping_cost - discount_amount
    WHERE order_id = p_order_id;
    
    SET p_result_message = CONCAT('Shipping calculated: $', p_shipping_cost, ' for ', p_shipping_method);
END$$

-- Procedure to generate sales report
CREATE PROCEDURE generate_report(
    IN p_start_date DATE,
    IN p_end_date DATE,
    IN p_report_type VARCHAR(50)
)
BEGIN
    IF p_report_type = 'SALES_SUMMARY' THEN
        SELECT 
            DATE(o.created_at) AS sale_date,
            COUNT(DISTINCT o.order_id) AS total_orders,
            COUNT(DISTINCT o.user_id) AS unique_customers,
            SUM(o.total_amount) AS daily_revenue,
            AVG(o.total_amount) AS avg_order_value,
            SUM(oi.quantity) AS total_items_sold
        FROM orders o
        LEFT JOIN order_items oi ON o.order_id = oi.order_id
        WHERE DATE(o.created_at) BETWEEN p_start_date AND p_end_date
          AND o.status NOT IN ('Cancelled', 'Refunded')
        GROUP BY DATE(o.created_at)
        ORDER BY sale_date DESC;
        
    ELSEIF p_report_type = 'TOP_PRODUCTS' THEN
        SELECT 
            p.product_id,
            p.sku,
            p.name,
            SUM(oi.quantity) AS total_sold,
            SUM(oi.total_price) AS total_revenue,
            COUNT(DISTINCT oi.order_id) AS order_count
        FROM products p
        JOIN order_items oi ON p.product_id = oi.product_id
        JOIN orders o ON oi.order_id = o.order_id
        WHERE DATE(o.created_at) BETWEEN p_start_date AND p_end_date
          AND o.status NOT IN ('Cancelled', 'Refunded')
        GROUP BY p.product_id, p.sku, p.name
        ORDER BY total_sold DESC
        LIMIT 50;
        
    ELSEIF p_report_type = 'CUSTOMER_ANALYSIS' THEN
        SELECT 
            u.user_id,
            u.username,
            u.email,
            COUNT(DISTINCT o.order_id) AS order_count,
            SUM(o.total_amount) AS total_spent,
            AVG(o.total_amount) AS avg_order_value,
            MAX(o.created_at) AS last_order_date
        FROM users u
        JOIN orders o ON u.user_id = o.user_id
        WHERE DATE(o.created_at) BETWEEN p_start_date AND p_end_date
          AND o.status NOT IN ('Cancelled', 'Refunded')
        GROUP BY u.user_id, u.username, u.email
        HAVING order_count >= 2
        ORDER BY total_spent DESC
        LIMIT 100;
    END IF;
END$$

DELIMITER ;

-- =============================================================================
-- FUNCTIONS (4 utility functions)
-- =============================================================================

DELIMITER $$

-- Function to calculate discount based on customer tier
CREATE FUNCTION calculate_discount(
    p_user_id INT,
    p_order_amount DECIMAL(12,2)
) 
RETURNS DECIMAL(12,2)
READS SQL DATA
DETERMINISTIC
BEGIN
    DECLARE v_subscription_type VARCHAR(20) DEFAULT 'Free';
    DECLARE v_total_purchases DECIMAL(12,2) DEFAULT 0.00;
    DECLARE v_discount_rate DECIMAL(5,4) DEFAULT 0.0000;
    DECLARE v_discount_amount DECIMAL(12,2) DEFAULT 0.00;
    
    -- Get customer information
    SELECT up.subscription_type, up.total_purchases
    INTO v_subscription_type, v_total_purchases
    FROM user_profiles up
    WHERE up.user_id = p_user_id;
    
    -- Calculate discount rate based on subscription and purchase history
    CASE v_subscription_type
        WHEN 'Premium' THEN
            SET v_discount_rate = 0.0500; -- 5%
        WHEN 'Enterprise' THEN
            SET v_discount_rate = 0.1000; -- 10%
        ELSE
            -- Free tier gets discount based on purchase history
            IF v_total_purchases >= 1000.00 THEN
                SET v_discount_rate = 0.0300; -- 3%
            ELSEIF v_total_purchases >= 500.00 THEN
                SET v_discount_rate = 0.0200; -- 2%
            ELSEIF v_total_purchases >= 100.00 THEN
                SET v_discount_rate = 0.0100; -- 1%
            END IF;
    END CASE;
    
    -- Calculate discount amount
    SET v_discount_amount = p_order_amount * v_discount_rate;
    
    -- Cap discount at $50 for free tier, $100 for premium, unlimited for enterprise
    IF v_subscription_type = 'Free' AND v_discount_amount > 50.00 THEN
        SET v_discount_amount = 50.00;
    ELSEIF v_subscription_type = 'Premium' AND v_discount_amount > 100.00 THEN
        SET v_discount_amount = 100.00;
    END IF;
    
    RETURN v_discount_amount;
END$$

-- Function to format currency values
CREATE FUNCTION format_currency(
    p_amount DECIMAL(12,2),
    p_currency VARCHAR(3)
)
RETURNS VARCHAR(20)
NO SQL
DETERMINISTIC
BEGIN
    DECLARE v_formatted VARCHAR(20);
    
    CASE p_currency
        WHEN 'USD' THEN
            SET v_formatted = CONCAT('$', FORMAT(p_amount, 2));
        WHEN 'EUR' THEN
            SET v_formatted = CONCAT('€', FORMAT(p_amount, 2));
        WHEN 'GBP' THEN
            SET v_formatted = CONCAT('£', FORMAT(p_amount, 2));
        WHEN 'JPY' THEN
            SET v_formatted = CONCAT('¥', FORMAT(p_amount, 0));
        ELSE
            SET v_formatted = CONCAT(p_currency, ' ', FORMAT(p_amount, 2));
    END CASE;
    
    RETURN v_formatted;
END$$

-- Function to validate email format
CREATE FUNCTION validate_email(p_email VARCHAR(255))
RETURNS BOOLEAN
NO SQL
DETERMINISTIC
BEGIN
    DECLARE v_is_valid BOOLEAN DEFAULT FALSE;
    
    -- Basic email validation using REGEXP
    IF p_email REGEXP '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$' THEN
        SET v_is_valid = TRUE;
    END IF;
    
    RETURN v_is_valid;
END$$

-- Function to get tax rate based on location
CREATE FUNCTION get_tax_rate(
    p_country VARCHAR(2),
    p_state_province VARCHAR(100)
)
RETURNS DECIMAL(5,4)
NO SQL
DETERMINISTIC
BEGIN
    DECLARE v_tax_rate DECIMAL(5,4) DEFAULT 0.0000;
    
    -- Tax rates by country/state
    CASE p_country
        WHEN 'US' THEN
            CASE p_state_province
                WHEN 'CA' THEN SET v_tax_rate = 0.0875; -- California
                WHEN 'NY' THEN SET v_tax_rate = 0.0800; -- New York
                WHEN 'TX' THEN SET v_tax_rate = 0.0625; -- Texas
                WHEN 'FL' THEN SET v_tax_rate = 0.0600; -- Florida
                ELSE SET v_tax_rate = 0.0500; -- Default US rate
            END CASE;
        WHEN 'CA' THEN
            SET v_tax_rate = 0.1300; -- Canada GST/HST
        WHEN 'GB' THEN
            SET v_tax_rate = 0.2000; -- UK VAT
        WHEN 'DE' THEN
            SET v_tax_rate = 0.1900; -- Germany VAT
        WHEN 'FR' THEN
            SET v_tax_rate = 0.2000; -- France VAT
        ELSE
            SET v_tax_rate = 0.0000; -- No tax for other countries
    END CASE;
    
    RETURN v_tax_rate;
END$$

DELIMITER ;

-- =============================================================================
-- TRIGGERS (3 triggers for audit and automation)
-- =============================================================================

DELIMITER $$

-- Trigger to audit user changes
CREATE TRIGGER users_audit_trigger
AFTER UPDATE ON users
FOR EACH ROW
BEGIN
    INSERT INTO audit_log (
        user_id, action, table_name, record_id,
        old_values, new_values, ip_address
    ) VALUES (
        NEW.user_id, 'UPDATE', 'users', NEW.user_id,
        JSON_OBJECT(
            'username', OLD.username,
            'email', OLD.email,
            'status', OLD.status,
            'last_login', OLD.last_login
        ),
        JSON_OBJECT(
            'username', NEW.username,
            'email', NEW.email,
            'status', NEW.status,
            'last_login', NEW.last_login
        ),
        @client_ip
    );
END$$

-- Trigger to update inventory tracking
CREATE TRIGGER inventory_update_trigger
AFTER UPDATE ON products
FOR EACH ROW
BEGIN
    IF OLD.stock_quantity != NEW.stock_quantity THEN
        INSERT INTO audit_log (
            action, table_name, record_id,
            old_values, new_values
        ) VALUES (
            'INVENTORY_UPDATE', 'products', NEW.product_id,
            JSON_OBJECT('stock_quantity', OLD.stock_quantity),
            JSON_OBJECT('stock_quantity', NEW.stock_quantity)
        );
        
        -- Alert if stock is low
        IF NEW.stock_quantity <= NEW.low_stock_threshold THEN
            INSERT INTO audit_log (
                action, table_name, record_id,
                new_values
            ) VALUES (
                'LOW_STOCK_ALERT', 'products', NEW.product_id,
                JSON_OBJECT(
                    'product_name', NEW.name,
                    'sku', NEW.sku,
                    'current_stock', NEW.stock_quantity,
                    'threshold', NEW.low_stock_threshold
                )
            );
        END IF;
    END IF;
END$$

-- Trigger to update order status timestamps
CREATE TRIGGER order_status_trigger
BEFORE UPDATE ON orders
FOR EACH ROW
BEGIN
    IF OLD.status != NEW.status THEN
        CASE NEW.status
            WHEN 'Shipped' THEN
                IF NEW.shipped_at IS NULL THEN
                    SET NEW.shipped_at = CURRENT_TIMESTAMP;
                END IF;
            WHEN 'Delivered' THEN
                IF NEW.delivered_at IS NULL THEN
                    SET NEW.delivered_at = CURRENT_TIMESTAMP;
                END IF;
                IF NEW.shipped_at IS NULL THEN
                    SET NEW.shipped_at = CURRENT_TIMESTAMP;
                END IF;
        END CASE;
        
        -- Log status change
        INSERT INTO audit_log (
            user_id, action, table_name, record_id,
            old_values, new_values
        ) VALUES (
            NEW.user_id, 'ORDER_STATUS_CHANGE', 'orders', NEW.order_id,
            JSON_OBJECT('status', OLD.status),
            JSON_OBJECT('status', NEW.status)
        );
    END IF;
END$$

DELIMITER ;

-- =============================================================================
-- EVENTS (2 scheduled events for maintenance)
-- =============================================================================

DELIMITER $$

-- Event to cleanup old audit logs (runs daily)
CREATE EVENT cleanup_old_logs
ON SCHEDULE EVERY 1 DAY
STARTS CURRENT_TIMESTAMP
DO
BEGIN
    -- Delete audit logs older than 1 year
    DELETE FROM audit_log 
    WHERE created_at < DATE_SUB(CURRENT_TIMESTAMP, INTERVAL 1 YEAR);
    
    -- Log cleanup action
    INSERT INTO audit_log (action, table_name, new_values)
    VALUES ('CLEANUP_EXECUTED', 'audit_log', 
            JSON_OBJECT('cleanup_date', CURRENT_TIMESTAMP));
END$$

-- Event to update daily statistics (runs at midnight)
CREATE EVENT update_statistics
ON SCHEDULE EVERY 1 DAY
STARTS (CURRENT_DATE + INTERVAL 1 DAY)
DO
BEGIN
    -- Update user profile purchase totals
    UPDATE user_profiles up
    SET total_purchases = (
        SELECT COALESCE(SUM(o.total_amount), 0)
        FROM orders o
        WHERE o.user_id = up.user_id 
          AND o.status NOT IN ('Cancelled', 'Refunded')
    );
    
    -- Update loyalty points (1 point per dollar spent)
    UPDATE user_profiles up
    SET loyalty_points = ROUND(up.total_purchases);
    
    -- Log statistics update
    INSERT INTO audit_log (action, table_name, new_values)
    VALUES ('STATISTICS_UPDATE', 'user_profiles', 
            JSON_OBJECT('update_date', CURRENT_DATE));
END$$

DELIMITER ;

-- =============================================================================
-- SAMPLE DATA INSERTION
-- =============================================================================

-- COMMENTED BY VIDEX
-- -- Insert sample categories
-- INSERT INTO categories (name, description, parent_id, is_active) VALUES
-- ('Electronics', 'Electronic devices and accessories', NULL, TRUE),
-- ('Computers', 'Computers and computer accessories', 1, TRUE),
-- ('Mobile Devices', 'Smartphones, tablets, and accessories', 1, TRUE),
-- ('Home & Garden', 'Home improvement and garden supplies', NULL, TRUE),
-- ('Furniture', 'Indoor and outdoor furniture', 4, TRUE),
-- ('Books', 'Books and educational materials', NULL, TRUE),
-- ('Fiction', 'Fiction books and novels', 6, TRUE),
-- ('Non-Fiction', 'Educational and reference books', 6, TRUE);

-- -- Insert sample users
-- INSERT INTO users (username, email, password_hash, first_name, last_name, phone, date_of_birth, gender, status, email_verified) VALUES
-- ('johndoe', 'john.doe@example.com', '$2y$10$hash1', 'John', 'Doe', '+1-555-0101', '1985-03-15', 'Male', 'Active', TRUE),
-- ('janesmithh', 'jane.smith@example.com', '$2y$10$hash2', 'Jane', 'Smith', '+1-555-0102', '1990-07-22', 'Female', 'Active', TRUE),
-- ('bobwilson', 'bob.wilson@example.com', '$2y$10$hash3', 'Bob', 'Wilson', '+1-555-0103', '1982-11-08', 'Male', 'Active', TRUE),
-- ('alicejohnson', 'alice.johnson@example.com', '$2y$10$hash4', 'Alice', 'Johnson', '+1-555-0104', '1995-01-30', 'Female', 'Pending', FALSE),
-- ('charlesdavis', 'charles.davis@example.com', '$2y$10$hash5', 'Charles', 'Davis', '+1-555-0105', '1978-09-12', 'Male', 'Active', TRUE);

-- -- Insert user profiles
-- INSERT INTO user_profiles (user_id, bio, timezone, language, currency, subscription_type, total_purchases, loyalty_points, referral_code) VALUES
-- (1, 'Tech enthusiast and early adopter', 'America/New_York', 'en', 'USD', 'Premium', 1250.75, 1251, 'REF001'),
-- (2, 'Love reading and home decoration', 'America/Los_Angeles', 'en', 'USD', 'Free', 425.50, 426, 'REF002'),
-- (3, 'Outdoor enthusiast and gardener', 'America/Chicago', 'en', 'USD', 'Enterprise', 2150.00, 2150, 'REF003'),
-- (4, 'Student and book lover', 'Europe/London', 'en', 'GBP', 'Free', 0.00, 0, 'REF004'),
-- (5, 'Business professional', 'America/New_York', 'en', 'USD', 'Premium', 875.25, 875, 'REF005');

-- -- Insert sample products
-- INSERT INTO products (sku, name, description, category_id, brand, price, cost, status, stock_quantity, featured) VALUES
-- ('LAPTOP001', 'High-Performance Laptop', 'Latest generation laptop with 16GB RAM and 512GB SSD', 2, 'TechBrand', 1299.99, 850.00, 'Active', 15, TRUE),
-- ('PHONE001', 'Smartphone Pro', 'Latest smartphone with advanced camera system', 3, 'PhoneCorp', 899.99, 600.00, 'Active', 25, TRUE),
-- ('BOOK001', 'Programming Guide', 'Comprehensive guide to modern programming', 8, 'TechBooks', 49.99, 25.00, 'Active', 100, FALSE),
-- ('CHAIR001', 'Ergonomic Office Chair', 'Comfortable office chair with lumbar support', 5, 'OfficeFurn', 299.99, 150.00, 'Active', 8, FALSE),
-- ('TABLET001', 'Tablet Pro 12"', 'Professional tablet with stylus support', 3, 'TabletInc', 649.99, 400.00, 'Active', 12, TRUE);

-- -- Insert sample system configuration
-- INSERT INTO system_config (config_key, config_value, config_type, description, is_public) VALUES
-- ('site_name', 'Advanced E-Commerce Store', 'string', 'The name of the website', TRUE),
-- ('currency_default', 'USD', 'string', 'Default currency for the store', TRUE),
-- ('tax_enabled', 'true', 'boolean', 'Whether tax calculation is enabled', FALSE),
-- ('free_shipping_threshold', '50.00', 'number', 'Minimum order amount for free shipping', TRUE),
-- ('max_login_attempts', '5', 'number', 'Maximum failed login attempts before account lock', FALSE);

-- =============================================================================
-- SUMMARY
-- =============================================================================

-- This source schema contains:
-- - 12 tables with comprehensive business logic
-- - 2 sequences for auto-numbering
-- - 4 complex views for analytics
-- - 4 stored procedures for business operations
-- - 4 utility functions
-- - 3 triggers for automation and auditing
-- - 2 scheduled events for maintenance
-- - Sample data in key tables

-- Total objects: 31 major database objects
-- This provides a solid foundation for testing complex DDL operations
-- and ensuring the DDL Wizard can handle enterprise-level database structures.
