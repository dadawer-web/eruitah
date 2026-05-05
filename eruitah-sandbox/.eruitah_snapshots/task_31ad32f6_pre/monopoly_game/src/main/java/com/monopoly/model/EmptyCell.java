package com.monopoly.model;

/**
 * 空地单元格 - 可以购买
 */
public class EmptyCell extends Cell {
    private int price;
    
    public EmptyCell(int id, String name, int price) {
        super(id, name, CellType.EMPTY);
        this.price = price;
    }
    
    @Override
    public void action(Player player) {
        // 空地可以被购买
        System.out.println(player.getName() + " 停在空地 " + getName() + "，价格: " + price);
        // 购买逻辑将在游戏服务层处理
    }
    
    public int getPrice() { return price; }
    public void setPrice(int price) { this.price = price; }
}