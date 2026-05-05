package com.monopoly.model;

/**
 * 游戏地图单元格基类
 */
public abstract class Cell {
    protected int id;
    protected String name;
    protected CellType type;
    
    public Cell(int id, String name, CellType type) {
        this.id = id;
        this.name = name;
        this.type = type;
    }
    
    public abstract void action(Player player);
    
    // Getters and Setters
    public int getId() { return id; }
    public void setId(int id) { this.id = id; }
    public String getName() { return name; }
    public void setName(String name) { this.name = name; }
    public CellType getType() { return type; }
    public void setType(CellType type) { this.type = type; }
}