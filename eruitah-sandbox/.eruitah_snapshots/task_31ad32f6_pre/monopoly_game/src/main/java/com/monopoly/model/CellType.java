package com.monopoly.model;

/**
 * 单元格类型枚举
 */
public enum CellType {
    EMPTY,          // 空地（可购买）
    PROPERTY,       // 房产
    LUCKY,          // 幸运
    UNLUCKY,        // 不幸
    START,          // 起点
    JAIL,           // 监狱
    HOSPITAL,       // 医院
    TAX             // 税务局
}