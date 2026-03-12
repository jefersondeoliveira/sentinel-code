package com.example.store.repository;

import com.example.store.model.User;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;
import java.util.List;

@Repository
public interface UserRepository extends JpaRepository<User, Long> {

    // PROBLEMA: findByEmail sem @Index em User.email → full table scan
    // → aciona MISSING_INDEX
    List<User> findByEmail(String email);

    // PROBLEMA: findByStatus sem @Index em User.status → full table scan
    // → aciona MISSING_INDEX
    List<User> findByStatus(String status);

    // PROBLEMA: findAll() sem Pageable → carrega toda a tabela em memória
    // → aciona PAGINATION
    List<User> findAll();
}
