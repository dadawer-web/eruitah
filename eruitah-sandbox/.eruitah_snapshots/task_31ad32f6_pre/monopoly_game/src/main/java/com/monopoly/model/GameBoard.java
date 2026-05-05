package com.monopoly.model;

import java.util.ArrayList;
import java.util.List;

/**
 * 游戏棋盘
 */
public class GameBoard {
    private List<Cell> cells;
    private List<Player> players;
    private int currentPlayerIndex;
    private boolean gameOver;
    private Player winner;
    
    public GameBoard() {
        this.cells = new ArrayList<>();
        this.players = new ArrayList<>();
        this.currentPlayerIndex = 0;
        this.gameOver = false;
        this.winner = null;
    }
    
    public void addCell(Cell cell) {
        cells.add(cell);
    }
    
    public void addPlayer(Player player) {
        players.add(player);
    }
    
    public Cell getCell(int position) {
        return cells.get(position);
    }
    
    public Player getCurrentPlayer() {
        return players.get(currentPlayerIndex);
    }
    
    public void nextPlayer() {
        currentPlayerIndex = (currentPlayerIndex + 1) % players.size();
    }
    
    public boolean isGameOver() {
        // 检查是否只有一个玩家未破产
        long alivePlayers = players.stream().filter(p -> !p.isBankrupt()).count();
        if (alivePlayers <= 1) {
            gameOver = true;
            players.stream().filter(p -> !p.isBankrupt()).findFirst().ifPresent(p -> winner = p);
            return true;
        }
        return false;
    }
    
    // Getters and Setters
    public List<Cell> getCells() { return cells; }
    public void setCells(List<Cell> cells) { this.cells = cells; }
    public List<Player> getPlayers() { return players; }
    public void setPlayers(List<Player> players) { this.players = players; }
    public int getCurrentPlayerIndex() { return currentPlayerIndex; }
    public void setCurrentPlayerIndex(int currentPlayerIndex) { this.currentPlayerIndex = currentPlayerIndex; }
    public Player getWinner() { return winner; }
    public void setWinner(Player winner) { this.winner = winner; }
}