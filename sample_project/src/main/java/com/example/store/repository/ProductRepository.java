package com.example.store.repository;

import com.example.store.model.Product;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;
import java.util.List;

@Repository
public interface ProductRepository extends JpaRepository<Product, Long> {

    // PROBLEMA: findByCategory sem @Index em Product.category → full table scan
    // → aciona MISSING_INDEX
    List<Product> findByCategory(String category);
}
