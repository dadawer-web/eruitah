package com.chat.ai.repository;

import com.chat.ai.model.graph.UserNode;
import org.springframework.data.neo4j.repository.Neo4jRepository;
import org.springframework.data.neo4j.repository.query.Query;

import java.util.List;
import java.util.Optional;

public interface UserRepository extends Neo4jRepository<UserNode, String> {

    Optional<UserNode> findByUserId(String userId);

    @Query("""
        MATCH (u:User)-[r:COGNITION]->(c:Concept)
        WHERE r.last_update >= timestamp() - 7 * 24 * 60 * 60 * 1000
        RETURN DISTINCT u
        """)
    List<UserNode> findAllActive();
}
