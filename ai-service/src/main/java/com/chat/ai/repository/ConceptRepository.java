package com.chat.ai.repository;

import com.chat.ai.model.graph.ConceptNode;
import org.springframework.data.neo4j.repository.Neo4jRepository;
import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

import java.util.List;

public interface ConceptRepository extends Neo4jRepository<ConceptNode, String> {

    @Query("""
        MATCH (root:Concept)
        WHERE root.name IN ['数据结构', '计算机操作系统', '计算机组成原理', '计算机网络']
        OPTIONAL MATCH (root)<-[:BELONGS_TO*1..10]-(leaf:Concept)
        OPTIONAL MATCH (leaf)<-[r:COGNITION]-(u:User {userId: $userId})
        WITH root.name AS subject, avg(r.score) AS avgScore
        RETURN subject, coalesce(avgScore, 0.0) AS mastery
        """)
    List<SubjectMasteryResult> calculateSubjectMasteryByUserId(@Param("userId") String userId);

    interface SubjectMasteryResult {
        String getSubject();
        Double getMastery();
    }
}
