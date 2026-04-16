package com.chat.ai.model.graph;

public record KnowledgeTriplet(
    String subject,
    String relation,
    String object,
    String rationale
) {
    public static final String RELATION_MASTERED = "掌握";
    public static final String RELATION_FUZZY = "模糊";
    public static final String RELATION_NOT_MASTERED = "未掌握";
    
    public boolean isMastered() {
        return RELATION_MASTERED.equals(relation);
    }
    
    public boolean isFuzzy() {
        return RELATION_FUZZY.equals(relation);
    }
    
    public boolean isNotMastered() {
        return RELATION_NOT_MASTERED.equals(relation);
    }
}
