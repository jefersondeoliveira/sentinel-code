package com.example.store.model;

import javax.persistence.Entity;
import javax.persistence.Id;

@Entity
// PROBLEMA: sem @Table(indexes=...) para o campo category
// → aciona MISSING_INDEX via findByCategory no ProductRepository
public class Product {

    @Id
    private Long id;

    private String name;
    private String category;  // sem @Index → MISSING_INDEX
    private Double price;

    // getters/setters omitidos para brevidade
}
