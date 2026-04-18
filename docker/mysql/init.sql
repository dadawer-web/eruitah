CREATE DATABASE IF NOT EXISTS `chat` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci;
USE `chat`;

CREATE TABLE IF NOT EXISTS `user` (
    `id` BIGINT PRIMARY KEY AUTO_INCREMENT,
    `name` VARCHAR(50) NOT NULL,
    `password` VARCHAR(100) NOT NULL,
    `state` VARCHAR(20) NOT NULL DEFAULT 'offline',
    `avatar` LONGBLOB DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `friend` (
    `userid` INT NOT NULL,
    `friendid` INT NOT NULL,
    PRIMARY KEY (`userid`, `friendid`),
    KEY `idx_friendid` (`friendid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `allgroup` (
    `id` INT PRIMARY KEY AUTO_INCREMENT,
    `groupname` VARCHAR(100) NOT NULL,
    `groupdesc` VARCHAR(200) DEFAULT ''
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `groupuser` (
    `groupid` INT NOT NULL,
    `userid` INT NOT NULL,
    `grouprole` VARCHAR(20) NOT NULL DEFAULT 'normal',
    PRIMARY KEY (`groupid`, `userid`),
    KEY `idx_userid` (`userid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `offlinemessage` (
    `userid` INT NOT NULL,
    `message` TEXT NOT NULL,
    KEY `idx_userid` (`userid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `emoji` (
    `id` BIGINT PRIMARY KEY AUTO_INCREMENT,
    `user_id` BIGINT NOT NULL,
    `name` VARCHAR(100) NOT NULL,
    `image_data` LONGBLOB NOT NULL,
    `create_time` DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (`user_id`) REFERENCES `user`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `farm_user` (
    `userid` INT NOT NULL,
    `coins` INT NOT NULL DEFAULT 0,
    `exp` INT NOT NULL DEFAULT 0,
    `total_planted` INT NOT NULL DEFAULT 0,
    `total_harvested` INT NOT NULL DEFAULT 0,
    `total_answered` INT NOT NULL DEFAULT 0,
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`userid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `farm_plot` (
    `id` INT AUTO_INCREMENT,
    `ownerid` INT NOT NULL,
    `plotindex` INT NOT NULL,
    `state` TINYINT NOT NULL DEFAULT 0,
    `question` TEXT,
    `subject` VARCHAR(10) DEFAULT NULL,
    `answererid` INT DEFAULT NULL,
    `answer` TEXT,
    `score` INT DEFAULT NULL,
    `feedback` TEXT,
    `planted_at` TIMESTAMP NULL,
    `answered_at` TIMESTAMP NULL,
    `harvested_at` TIMESTAMP NULL,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_owner_plot` (`ownerid`, `plotindex`),
    KEY `idx_state` (`state`),
    KEY `idx_ownerid` (`ownerid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `farm_log` (
    `id` BIGINT AUTO_INCREMENT,
    `userid` INT NOT NULL,
    `action` VARCHAR(20) NOT NULL,
    `plotid` INT,
    `target_userid` INT,
    `detail` TEXT,
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    KEY `idx_userid` (`userid`),
    KEY `idx_created` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
