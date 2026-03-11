package com.example.demo.repository;

import com.example.demo.model.User;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.List;

/**
 * PROBLEMAS DE PERFORMANCE INTENCIONAIS (sample para SentinelCode Fase 3):
 *
 * 1. findByEmail / findByStatus — sem @Index na entidade User
 *    → resulta em full table scan com 1M+ registros
 *
 * 2. List<User> findAll() — sem paginação
 *    → pode carregar toda a tabela em memória (OOM em produção)
 */
@Repository
public interface UserRepository extends JpaRepository<User, Long> {

    // PROBLEMA: sem @Index em email na entidade User
    List<User> findByEmail(String email);

    // PROBLEMA: sem @Index em status
    List<User> findByStatus(String status);

    // PROBLEMA: sem @Index em username + status (índice composto necessário)
    List<User> findByUsernameAndStatus(String username, String status);

    // PROBLEMA: findAll sem Pageable — carrega toda a tabela
    List<User> findAll();
}
