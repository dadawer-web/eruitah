package com.chat.ai.repository;

import com.chat.ai.model.graph.UserNode;
import org.springframework.data.neo4j.repository.Neo4jRepository;

import java.util.Optional;

public interface UserRepository extends Neo4jRepository<UserNode, String> {

    Optional<UserNode> findByUserId(String userId);
}
