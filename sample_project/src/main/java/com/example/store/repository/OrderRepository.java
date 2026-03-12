package com.example.store.repository;

import com.example.store.model.Order;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;
import java.util.List;

@Repository
public interface OrderRepository extends JpaRepository<Order, Long> {

    // PROBLEMA: findAll() sem Pageable → carrega toda a tabela em memória
    // → aciona PAGINATION
    List<Order> findAll();

    // PROBLEMA: findByUsernameAndStatus sem @Index composto → full scan
    // → aciona MISSING_INDEX
    List<Order> findByUsernameAndStatus(String username, String status);
}
