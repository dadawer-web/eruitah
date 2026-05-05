package com.monopoly.dao;

import com.monopoly.model.Cell;
import java.util.List;

/**
 * 地图数据访问接口
 */
public interface MapDAO {
    List<Cell> loadMap();
    void saveMap(List<Cell> cells);
}