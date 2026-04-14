-- 408农场数据库表设计
-- 在 chat 数据库中执行

-- 农场用户数据表（扩展用户表，记录金币和经验）
CREATE TABLE IF NOT EXISTS `farm_user` (
    `userid` INT NOT NULL COMMENT '用户ID，关联user表',
    `coins` INT NOT NULL DEFAULT 0 COMMENT '金币（收菜奖励）',
    `exp` INT NOT NULL DEFAULT 0 COMMENT '经验值（提问奖励）',
    `total_planted` INT NOT NULL DEFAULT 0 COMMENT '总种植次数',
    `total_harvested` INT NOT NULL DEFAULT 0 COMMENT '总收割次数（自己被答对）',
    `total_answered` INT NOT NULL DEFAULT 0 COMMENT '总答题次数',
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`userid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='农场用户数据';

-- 农场地块表（每个用户9个坑位）
CREATE TABLE IF NOT EXISTS `farm_plot` (
    `id` INT AUTO_INCREMENT COMMENT '地块自增ID',
    `ownerid` INT NOT NULL COMMENT '地块所有者用户ID',
    `plotindex` INT NOT NULL COMMENT '地块索引0-8',
    `state` TINYINT NOT NULL DEFAULT 0 COMMENT '0=空地 1=生长中 2=成熟 3=已收割',
    `question` TEXT COMMENT '种下的问题',
    `subject` VARCHAR(10) DEFAULT NULL COMMENT '科目标签(OS/NET/DS/CO)',
    `answererid` INT DEFAULT NULL COMMENT '答题者ID',
    `answer` TEXT COMMENT '答题者的答案',
    `score` INT DEFAULT NULL COMMENT 'AI评分',
    `feedback` TEXT COMMENT 'AI评语',
    `planted_at` TIMESTAMP NULL COMMENT '种植时间',
    `answered_at` TIMESTAMP NULL COMMENT '答题时间',
    `harvested_at` TIMESTAMP NULL COMMENT '收割时间',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_owner_plot` (`ownerid`, `plotindex`),
    KEY `idx_state` (`state`),
    KEY `idx_ownerid` (`ownerid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='农场地块';

-- 农场操作日志表（用于全服广播和统计）
CREATE TABLE IF NOT EXISTS `farm_log` (
    `id` BIGINT AUTO_INCREMENT COMMENT '日志ID',
    `userid` INT NOT NULL COMMENT '操作用户ID',
    `action` VARCHAR(20) NOT NULL COMMENT '操作类型: plant/answer/harvest',
    `plotid` INT COMMENT '地块ID',
    `target_userid` INT COMMENT '目标用户ID（答题/收割对象）',
    `detail` TEXT COMMENT '操作详情JSON',
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    KEY `idx_userid` (`userid`),
    KEY `idx_created` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='农场操作日志';

-- 为所有现有用户初始化农场数据（可选执行）
-- INSERT INTO farm_user (userid) SELECT id FROM user WHERE id NOT IN (SELECT userid FROM farm_user);

-- 为所有现有用户初始化9个空地块（可选执行）
-- INSERT INTO farm_plot (ownerid, plotindex, state) 
-- SELECT u.id, p.idx, 0 FROM user u CROSS JOIN (SELECT 0 AS idx UNION SELECT 1 UNION SELECT 2 UNION SELECT 3 UNION SELECT 4 UNION SELECT 5 UNION SELECT 6 UNION SELECT 7 UNION SELECT 8) p
-- WHERE NOT EXISTS (SELECT 1 FROM farm_plot fp WHERE fp.ownerid = u.id AND fp.plotindex = p.idx);
